"""
instructors.py — ماژول مدیریت اساتید (v3.11.0)
================================================================
- جدول instructors با فیلدهای: ردیف، کد، نام، نام کاربری، گروه، نوع همکاری
- نوع همکاری: هیات علمی، دستیارآموزشی، هیات علمی وابسته، حق التدریس
- سرویس واکشی از سامانه برنامه‌ریزی (پورت 8083) — با access_token bearer
- CRUD کامل + آپلود اکسل + پیش‌فرض
- همگام‌سازی اساتید به authorized_users (با نام کاربری/رمز یکسان)

مهم:
- کاملاً additive — هیچ تغییری در جداول موجود داده نمی‌شود.
"""

import os
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("instructors")

try:
    import requests
except ImportError:
    requests = None

# ==================================================
# مسیرها و ثابت‌ها
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTRUCTORS_SYNC_FILE = os.path.join(BASE_DIR, "instructors_sync.json")

# انواع همکاری معتبر (مطابق درخواست کاربر)
COOPERATION_TYPES = [
    "هیات علمی",
    "دستیارآموزشی",
    "هیات علمی وابسته",
    "حق التدریس",
]

# ==================================================
# Migration: ساخت جدول instructors
# ==================================================

def ensure_instructors_table(db):
    """
    ساخت جدول instructors در صورت عدم وجود.
    کاملاً additive.
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS instructors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                row_number INTEGER,
                code TEXT UNIQUE,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                email TEXT,
                "group" TEXT,
                cooperation_type TEXT,
                max_teaching_units INTEGER DEFAULT 0,
                role TEXT DEFAULT 'instructor',
                is_active INTEGER DEFAULT 1,
                password_hash TEXT,
                external_id INTEGER,
                source TEXT DEFAULT 'local',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # مایگریشن: افزودن ستون‌های جدید به جدول instructors موجود (اگر قبلاً با schema قدیمی ساخته شده)
        # این کار را قبل از ساخت ایندکس‌ها انجام می‌دهیم تا ستون‌ها موجود باشند
        for col, col_def in [
            ("row_number", "INTEGER"),
            ("full_name", "TEXT"),
            ("phone", "TEXT"),
            ("email", "TEXT"),
            ('"group"', "TEXT"),
            ("max_teaching_units", "INTEGER DEFAULT 0"),
            ("role", "TEXT DEFAULT 'instructor'"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("password_hash", "TEXT"),
            ("external_id", "INTEGER"),
            ("source", "TEXT DEFAULT 'local'"),
            ("updated_at", "TIMESTAMP"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE instructors ADD COLUMN {col} {col_def}")
            except Exception:
                pass  # ستون قبلاً وجود دارد

        # ایندکس‌ها (بعد از اطمینان از وجود ستون‌ها)
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instructors_code ON instructors(code)")
        except Exception:
            pass
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instructors_username ON instructors(username)")
        except Exception:
            pass
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_instructors_phone ON instructors(phone)")
        except Exception:
            pass

        # افزودن ستون user_type به authorized_users (اگر وجود ندارد)
        try:
            cursor.execute("ALTER TABLE authorized_users ADD COLUMN user_type TEXT DEFAULT 'student'")
            # ستون تازه اضافه شد — تمام رکوردهای فعلی student می‌شوند (DEFAULT)
        except Exception:
            pass  # اگر قبلاً اضافه شده

        # بازسازی جدول authorized_users برای حذف CHECK constraint قدیمی روی role
        # این کار فقط یک بار انجام می‌شود (با تشخیص از طریق schema)
        # باید در یک کانکشن مستقل و خارج از transaction فعلی انجام شود
        try:
            schema_row = cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='authorized_users'").fetchone()
            needs_rebuild = schema_row and "CHECK(role IN" in (schema_row[0] or "")
        except Exception:
            needs_rebuild = False

        if needs_rebuild:
            # commit 当前 transaction قبل از rebuild
            conn.commit()
            # کانکشن مستقل برای rebuild (PRAGMA foreign_keys باید خارج از transaction باشد)
            rebuild_conn = sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
            try:
                rebuild_conn.execute("PRAGMA foreign_keys=OFF")
                rebuild_conn.execute("CREATE TABLE IF NOT EXISTS authorized_users_new (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, display_phone TEXT NOT NULL, normalized_phone TEXT NOT NULL UNIQUE, student_number TEXT UNIQUE, student_type TEXT CHECK(student_type IN('پیوسته','ناپیوسته')), role TEXT DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, bale_id INTEGER, last_seen TIMESTAMP, is_blocked INTEGER DEFAULT 0, first_channel TEXT, password_hash TEXT, user_type TEXT DEFAULT 'student')")
                rebuild_conn.execute("INSERT INTO authorized_users_new (id, name, display_phone, normalized_phone, student_number, student_type, role, created_at, bale_id, last_seen, is_blocked, first_channel, password_hash, user_type) SELECT id, name, display_phone, normalized_phone, student_number, student_type, role, created_at, bale_id, last_seen, is_blocked, first_channel, password_hash, COALESCE(user_type, 'student') FROM authorized_users")
                rebuild_conn.execute("DROP TABLE authorized_users")
                rebuild_conn.execute("ALTER TABLE authorized_users_new RENAME TO authorized_users")
                rebuild_conn.commit()
                rebuild_conn.execute("PRAGMA foreign_keys=ON")
                logger.info("✓ authorized_users table rebuilt without old CHECK constraint on role")
            except Exception as e:
                logger.warning(f"rebuild authorized_users error: {e}")
                try:
                    rebuild_conn.rollback()
                except Exception:
                    pass
            finally:
                rebuild_conn.close()
            # refresh cursor
            cursor = conn.cursor()

        # آپدیت رکوردهای موجود: اگر user_type خالی است، پیش‌فرض student
        try:
            cursor.execute("UPDATE authorized_users SET user_type = 'student' WHERE user_type IS NULL OR user_type = ''")
        except Exception:
            pass

        # اگر نقش instructor است و user_type ست نشده، آن را instructor کن
        try:
            cursor.execute("UPDATE authorized_users SET user_type = 'instructor' WHERE role = 'instructor' AND (user_type IS NULL OR user_type = '' OR user_type = 'student')")
        except Exception:
            pass

        # اگر نقش admin است، user_type را admin کن
        try:
            cursor.execute("UPDATE authorized_users SET user_type = 'admin' WHERE role = 'admin' AND (user_type IS NULL OR user_type = '' OR user_type = 'student')")
        except Exception:
            pass

        conn.commit()
        logger.info("✓ instructors table ensured (with column migrations + user_type defaults)")
    return True


# ==================================================
# تنظیمات سرویس واکشی (mirror file)
# ==================================================

DEFAULT_SYNC_SETTINGS = {
    "enabled": False,
    "service_url": "http://188.212.96.235:8083",
    "username": "admin",
    "password": "admin123",
    "auto_sync": False,
    "sync_interval_minutes": 60,
    "last_sync_at": "",
    "last_sync_count": 0,
}


def load_sync_settings() -> Dict[str, Any]:
    data = {}
    if os.path.exists(INSTRUCTORS_SYNC_FILE):
        try:
            with open(INSTRUCTORS_SYNC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    settings = dict(DEFAULT_SYNC_SETTINGS)
    for k, v in data.items():
        settings[k] = v
    return settings


def save_sync_settings(settings: Dict[str, Any]) -> bool:
    try:
        with open(INSTRUCTORS_SYNC_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"save_sync_settings error: {e}")
        return False


# ==================================================
# CRUD: اساتید
# ==================================================

def get_all_instructors(db, search: str = "", cooperation_type: str = "") -> List[Dict[str, Any]]:
    query = 'SELECT * FROM instructors WHERE 1=1'
    params = []
    if search:
        query += ' AND (full_name LIKE ? OR code LIKE ? OR username LIKE ? OR phone LIKE ?)'
        like = f"%{search}%"
        params.extend([like, like, like, like])
    if cooperation_type:
        query += ' AND cooperation_type = ?'
        params.append(cooperation_type)
    query += ' ORDER BY row_number, id DESC'
    rows = db.execute_query(query, tuple(params))
    if rows is None:
        return []
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def get_instructor_by_id(db, instructor_id: int) -> Optional[Dict[str, Any]]:
    rows = db.execute_query("SELECT * FROM instructors WHERE id = ?", (instructor_id,))
    if not rows:
        return None
    return dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]


def create_instructor(db, data: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    from src.database import hash_password
    password = data.get("password", "")
    password_hash = hash_password(password) if password else None

    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        full_name = f"{first} {last}".strip()
    if not full_name:
        full_name = data.get("name", "").strip()

    query = '''
        INSERT INTO instructors
            (row_number, code, username, full_name, phone, email,
             "group", cooperation_type, max_teaching_units, role, is_active,
             password_hash, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (
        int(data.get("row_number") or 0),
        data.get("code", ""),
        data.get("username", ""),
        full_name,
        data.get("phone", ""),
        data.get("email", ""),
        data.get("group", "") or data.get("expert_group", ""),
        data.get("cooperation_type", ""),
        int(data.get("max_teaching_units") or 0),
        data.get("role", "instructor"),
        1 if data.get("is_active", True) else 0,
        password_hash,
        data.get("source", "local"),
    )
    result = db.execute_query(query, params)
    if result is None:
        return None, "خطا در ذخیره‌سازی"
    rows = db.execute_query("SELECT last_insert_rowid() AS id")
    if rows:
        return (rows[0]["id"] if isinstance(rows[0], dict) else rows[0][0]), None
    return 0, None


def update_instructor(db, instructor_id: int, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    existing = db.execute_query("SELECT id FROM instructors WHERE id = ?", (instructor_id,))
    if not existing:
        return False, "استاد پیدا نشد"

    from src.database import hash_password
    password = data.get("password")
    password_hash_clause = ""
    extra_params = []
    if password:
        password_hash_clause = ", password_hash = ?"
        extra_params.append(hash_password(password))

    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        full_name = data.get("name", "").strip()

    query = f'''
        UPDATE instructors SET
            row_number = ?, code = ?, username = ?, full_name = ?,
            phone = ?, email = ?, "group" = ?, cooperation_type = ?,
            max_teaching_units = ?, role = ?, is_active = ?,
            updated_at = CURRENT_TIMESTAMP
            {password_hash_clause}
        WHERE id = ?
    '''
    params = [
        int(data.get("row_number") or 0),
        data.get("code", ""),
        data.get("username", ""),
        full_name,
        data.get("phone", ""),
        data.get("email", ""),
        data.get("group", ""),
        data.get("cooperation_type", ""),
        int(data.get("max_teaching_units") or 0),
        data.get("role", "instructor"),
        1 if data.get("is_active", True) else 0,
    ] + extra_params + [instructor_id]

    result = db.execute_query(query, tuple(params))
    return (result is not None), None


def delete_instructor(db, instructor_id: int) -> Tuple[bool, Optional[str]]:
    existing = db.execute_query("SELECT id FROM instructors WHERE id = ?", (instructor_id,))
    if not existing:
        return False, "استاد پیدا نشد"
    db.execute_query("DELETE FROM instructors WHERE id = ?", (instructor_id,))
    return True, None


# ==================================================
# سرویس واکشی از سامانه برنامه‌ریزی (8083)
# ==================================================

def _login_to_remote(service_url: str, username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    """ورود به سامانه برنامه‌ریزی و گرفتن access_token."""
    base = service_url.rstrip("/")
    try:
        if requests is None:
            return None, "کتابخانه requests نصب نیست"
        resp = requests.post(
            f"{base}/api/auth/login",
            json={"username": username, "password": password},
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token") or data.get("token"), None
        else:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = resp.text[:200]
            return None, f"خطا در ورود (HTTP {resp.status_code}): {detail}"
    except Exception as e:
        return None, f"ارتباط با سرویس ناموفق: {e}"


def fetch_instructors_from_remote(service_url: str, username: str = "", password: str = "") -> Tuple[Optional[List[Dict]], Optional[str]]:
    """واکشی اساتید از سامانه برنامه‌ریزی."""
    if not service_url:
        return None, "service_url_not_configured"

    base = service_url.rstrip("/")

    # ۱) تلاش برای ورود
    auth_token = None
    if username and password:
        auth_token, err = _login_to_remote(base, username, password)
        if err:
            logger.warning(f"login failed: {err}")
            # ادامه با حالت بدون auth
        else:
            logger.info("✓ ورود به سامانه برنامه‌ریزی موفق")
    else:
        return None, "نام کاربری و رمز عبور سرویس تنظیم نشده است"

    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    # ۲) واکشی اساتید
    endpoints_to_try = [
        "/api/professors-rooms/instructors/list",
        "/api/professors-rooms/instructors",
        "/api/courses/instructors",
    ]
    last_err = None
    for ep in endpoints_to_try:
        try:
            resp = requests.get(f"{base}{ep}", headers=headers, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                # می‌تواند list یا dict با key باشد
                if isinstance(data, list):
                    return data, None
                elif isinstance(data, dict):
                    for key in ("items", "data", "instructors", "results"):
                        if key in data and isinstance(data[key], list):
                            return data[key], None
                    return [data], None
            elif resp.status_code == 401:
                last_err = "احراز هویت ناموفق بود — توکن نامعتبر است"
            else:
                last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = str(e)
            continue

    return None, last_err or "همه endpointها ناموفق بودند"


def sync_instructors_from_remote(db, settings: Dict[str, Any] = None) -> Dict[str, Any]:
    """همگام‌سازی اساتید از سامانه برنامه‌ریزی."""
    if settings is None:
        settings = load_sync_settings()

    if not settings.get("enabled"):
        return {"ok": False, "error": "sync_disabled", "message": "همگام‌سازی غیرفعال است. ابتدا آن را فعال کنید."}

    remote_data, err = fetch_instructors_from_remote(
        service_url=settings.get("service_url", ""),
        username=settings.get("username", ""),
        password=settings.get("password", ""),
    )

    if err:
        return {"ok": False, "error": err,
                "message": f"خطا در واکشی از سامانه برنامه‌ریزی: {err}"}

    synced_count = 0
    updated_count = 0
    errors = []
    for item in (remote_data or []):
        try:
            code = str(item.get("code") or item.get("instructor_code") or item.get("id") or "")
            full_name = (item.get("name") or item.get("full_name") or
                         f"{item.get('first_name', '')} {item.get('last_name', '')}".strip())
            if not code and not full_name:
                continue

            data = {
                "row_number": int(item.get("row_number") or 0),
                "code": code,
                "username": (item.get("username") or "").lstrip("@") or code,
                "full_name": full_name,
                "phone": item.get("phone") or item.get("mobile") or "",
                "email": item.get("email", ""),
                "group": item.get("group") or item.get("expert_group", ""),
                "cooperation_type": item.get("cooperation_type") or "",
                "max_teaching_units": int(item.get("max_teaching_units") or 0),
                "is_active": True,
                "source": "remote",
            }
            # update or insert
            existing = db.execute_query(
                "SELECT id FROM instructors WHERE code = ?", (code,)
            )
            if existing:
                eid = existing[0]["id"] if isinstance(existing[0], dict) else existing[0][0]
                ok, err_msg = update_instructor(db, eid, data)
                if ok:
                    updated_count += 1
                    synced_count += 1
                else:
                    errors.append(f"خطا در ویرایش {code}: {err_msg}")
            else:
                inst_id, err_msg = create_instructor(db, data)
                if err_msg:
                    errors.append(f"خطا در افزودن {code}: {err_msg}")
                else:
                    synced_count += 1
        except Exception as e:
            errors.append(f"{item.get('code', '?')}: {e}")

    # ذخیره زمان آخرین sync
    settings["last_sync_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    settings["last_sync_count"] = synced_count
    save_sync_settings(settings)

    # بررسی واقعی تعداد رکوردها در دیتابیس
    try:
        verify_rows = db.execute_query("SELECT COUNT(*) AS c FROM instructors")
        actual_count = verify_rows[0]["c"] if verify_rows else 0
    except Exception:
        actual_count = -1

    return {
        "ok": True,
        "synced": synced_count,
        "updated": updated_count,
        "new": synced_count - updated_count,
        "actual_in_db": actual_count,
        "errors": errors[:5],
        "message": f"{synced_count} استاد همگام‌سازی شد ({updated_count} به‌روز، {synced_count - updated_count} جدید). تعداد فعلی در DB: {actual_count}",
    }


# ==================================================
# آپلود اکسل اساتید
# ==================================================

EXCEL_MAP = {
    "ردیف": "row_number",
    "کد": "code",
    "کد استاد": "code",
    "نام و نام خانوادگی": "full_name",
    "نام": "full_name",
    "نام کاربری": "username",
    "تلفن": "phone",
    "شماره تلفن": "phone",
    "تلفن همراه": "phone",
    "ایمیل": "email",
    "گروه": "group",
    "گروه تخصصی": "group",
    "نوع همکاری": "cooperation_type",
    "حداکثر واحد": "max_teaching_units",
    "حداکثر واحد تدریس": "max_teaching_units",
    "نقش": "role",
    "وضعیت": "is_active",
}


def import_instructors_excel(db, file_path: str) -> Dict[str, Any]:
    try:
        import pandas as pd
    except ImportError:
        return {"ok": False, "count": 0, "errors": ["کتابخانه pandas نصب نیست"]}

    try:
        df = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        return {"ok": False, "count": 0, "errors": [f"خطا در خواندن فایل: {e}"]}

    df.columns = [str(c).strip().replace("  ", " ").replace("\u200c", "") for c in df.columns]
    logger.info(f"ستون‌های شناسایی‌شده: {list(df.columns)}")

    # بررسی ستون‌های ضروری
    if not any(c in df.columns for c in ["نام و نام خانوادگی", "نام"]):
        return {"ok": False, "count": 0,
                "errors": ["ستون‌های ضروری وجود ندارند: نام یا نام و نام خانوادگی"]}

    success_count = 0
    errors = []
    for idx, row in df.iterrows():
        row_dict = {}
        for fa_name, en_name in EXCEL_MAP.items():
            if fa_name in df.columns:
                val = row[fa_name]
                if pd.isna(val):
                    val = None
                else:
                    val = str(val).strip()
                    if en_name in ("row_number", "max_teaching_units") and val and val.replace(".", "").isdigit():
                        try:
                            val = int(float(val))
                        except Exception:
                            pass
                    elif en_name == "is_active":
                        val_lower = str(val).lower() if val else ""
                        val = val_lower in ("true", "1", "yes", "فعال")
                row_dict[en_name] = val

        full_name = row_dict.get("full_name") or row_dict.get("name") or ""
        if not full_name:
            errors.append(f"ردیف {idx + 2}: نام خالی است")
            continue

        if not row_dict.get("code"):
            row_dict["code"] = row_dict.get("username") or full_name
        if not row_dict.get("username"):
            row_dict["username"] = row_dict.get("code")

        # اگر code تکراری بود، update کن
        existing = db.execute_query(
            "SELECT id FROM instructors WHERE code = ?", (row_dict.get("code"),)
        )
        if existing:
            eid = existing[0]["id"] if isinstance(existing[0], dict) else existing[0][0]
            ok, err = update_instructor(db, eid, row_dict)
        else:
            _, err = create_instructor(db, row_dict)
            ok = err is None

        if ok:
            success_count += 1
        else:
            errors.append(f"ردیف {idx + 2}: {err}")

    return {
        "ok": success_count > 0,
        "count": success_count,
        "errors": errors[:10],
        "message": f"{success_count} استاد با موفقیت بارگذاری شد.",
    }


# ==================================================
# همگام‌سازی اساتید به authorized_users
# ==================================================

def sync_instructors_to_users(db, default_password: str = "Instructor@1405") -> Dict[str, Any]:
    """
    افزودن اساتید به جدول authorized_users (با نقش instructor) اگر قبلاً ثبت نشده‌اند.
    مهم: نام کاربری و رمز عبور یکسان هستند (رمز = نام کاربری هر استاد).
    """
    from src.database import hash_password

    instructors = get_all_instructors(db)
    if not instructors:
        return {"ok": False, "message": "هیچ استادی در جدول instructors وجود ندارد."}

    added_count = 0
    skipped_count = 0
    errors = []

    # گرفتن لیست username های موجود برای جلوگیری از تکرار
    existing_usernames = set()
    try:
        existing_rows = db.execute_query("SELECT student_number FROM authorized_users WHERE student_number IS NOT NULL")
        for r in (existing_rows or []):
            existing_usernames.add(r["student_number"] if isinstance(r, dict) else r[0])
    except Exception:
        pass

    # گرفتن لیست phone های موجود برای جلوگیری از duplicate UNIQUE
    existing_phones = set()
    try:
        existing_phone_rows = db.execute_query("SELECT normalized_phone FROM authorized_users WHERE normalized_phone IS NOT NULL")
        for r in (existing_phone_rows or []):
            existing_phones.add(r["normalized_phone"] if isinstance(r, dict) else r[0])
    except Exception:
        pass

    for inst in instructors:
        try:
            inst_dict = dict(inst) if not isinstance(inst, dict) else inst
            username = inst_dict.get("username") or inst_dict.get("code")
            full_name = inst_dict.get("full_name") or ""
            phone = inst_dict.get("phone") or ""
            code = inst_dict.get("code") or ""

            if not username:
                continue

            # بررسی تکراری نبودن با student_number
            if username in existing_usernames:
                skipped_count += 1
                continue

            # ساخت phone منحصر به فرد برای جلوگیری از UNIQUE constraint
            # اگر تلفن خالی است یا تکراری، از username استفاده کن
            if not phone or phone == "-" or phone == "":
                phone = username
            # اگر این phone قبلاً استفاده شده، username را به آن اضافه کن
            if phone in existing_phones:
                phone = f"{username}_{phone}"

            # رمز عبور = نام کاربری
            password = username
            pw_hash = hash_password(password)

            # INSERT مستقیم (با user_type)
            try:
                result = db.execute_query(
                    '''INSERT INTO authorized_users
                       (name, display_phone, normalized_phone, student_number, student_type, role, first_channel, password_hash, user_type)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (full_name or username, phone, phone, username, "ناپیوسته", "instructor", "instructor_sync", pw_hash, "instructor")
                )
                if result is not None:
                    added_count += 1
                    existing_usernames.add(username)
                    existing_phones.add(phone)
                else:
                    errors.append(f"خطا در افزودن {username}")
            except Exception as e:
                errors.append(f"{username}: {e}")
        except Exception as e:
            errors.append(f"{inst_dict.get('username', '?')}: {e}")

    return {
        "ok": added_count > 0 or skipped_count > 0,
        "added": added_count,
        "skipped": skipped_count,
        "total": len(instructors),
        "errors": errors[:5],
        "message": f"{added_count} استاد به کاربران سامانه اضافه شد (رمز عبور = نام کاربری). {skipped_count} استاد قبلاً وجود داشت.",
    }


# ==================================================
# پیش‌فرض اساتید
# ==================================================

def seed_default_instructors(db):
    """ساخت چند استاد پیش‌فرض اگر جدول خالی باشد."""
    count_rows = db.execute_query("SELECT COUNT(*) AS c FROM instructors")
    if count_rows and count_rows[0]["c"] > 0:
        return False

    defaults = [
        {"row_number": 1, "code": "1", "username": "ahmadi", "full_name": "محمد احمدی",
         "phone": "09121111111", "group": "مهندسی کامپیوتر", "cooperation_type": "هیات علمی",
         "max_teaching_units": 12, "password": "Instructor@1405"},
        {"row_number": 2, "code": "2", "username": "rezaei", "full_name": "علی رضایی",
         "phone": "09122222222", "group": "مهندسی برق", "cooperation_type": "دستیارآموزشی",
         "max_teaching_units": 10, "password": "Instructor@1405"},
        {"row_number": 3, "code": "3", "username": "karimi", "full_name": "زهرا کریمی",
         "phone": "09123333333", "group": "علوم کامپیوتر", "cooperation_type": "حق التدریس",
         "max_teaching_units": 8, "password": "Instructor@1405"},
    ]

    for d in defaults:
        create_instructor(db, d)

    logger.info(f"✓ {len(defaults)} default instructors created")
    return True
