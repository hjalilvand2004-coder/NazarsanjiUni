"""
preferences.py — ماژول مطلوبیت‌های تدریس و زمان‌بندی اساتید
================================================================
پیاده‌سازی کامل قابلیت مطلوبیت‌ها بدون آسیب به دیتابیس فعلی.

جداول جدید:
- teaching_preferences: مطلوبیت‌های تدریس (کدام استاد کدام درس را می‌خواهد)
- time_preferences: مطلوبیت‌های زمان‌بندی (کدام استاد در کدام بازه می‌خواهد)
- instructors: لیست اساتید (در صورت عدم وجود، از authorized_users با role != user ساخته می‌شود)

مهم:
- جداول فقط در صورت عدم وجود ساخته می‌شوند (CREATE TABLE IF NOT EXISTS)
- هیچ تغییری در جداول فعلی داده نمی‌شود
- مایگریشن ستون‌ها داخل try/except انجام می‌شود
"""

import os
import sqlite3
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("preferences")

# ==================================================
# ماژول slot_times (منبع مرجع)
# ==================================================

from slot_times import (
    DAY_MAP, DAY_NAMES_FA,
    normalize_day, normalize_term, get_slots,
    is_valid_slot, get_period_for_time,
    get_terms, get_schedule,
)


# ==================================================
# توابع کمکی نرمال‌سازی
# ==================================================

def normalize_code(code):
    """نرمال‌سازی کد درس: حذف فاصله/خط تیره، تبدیل ارقام فارسی/عربی به لاتین، حذف صفرهای ابتدایی."""
    if not code:
        return ""
    s = str(code).strip()
    # تبدیل ارقام فارسی/عربی
    persian_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    s = s.translate(persian_map)
    # حذف فاصله و خط تیره
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    # حذف صفرهای ابتدایی
    if s.isdigit():
        s = str(int(s))
    return s


def normalize_instructor_code(code):
    """نرمال‌سازی کد استاد: تبدیل ارقام فارسی/عربی، حذف فاصله‌ها."""
    if not code:
        return ""
    s = str(code).strip()
    persian_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    s = s.translate(persian_map)
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    return s


# ==================================================
# اولویت نوع همکاری (از COOPERATION_PRIORITY در پروژه مرجع)
# ==================================================

COOPERATION_PRIORITY = {
    "هیئت علمی": 1,    # بالاترین اولویت
    "تمام‌وقت": 1,
    "نیم‌وقت": 2,
    "ساعتی": 3,
    "مهمان": 4,
    "قراردادی": 4,
    # معادل‌های انگلیسی
    "full_time": 1, "fulltime": 1,
    "part_time": 2, "parttime": 2,
    "hourly": 3, "guest": 4, "contract": 4,
}


def get_cooperation_priority(coop_type):
    """گرفتن اولویت عددی نوع همکاری (کوچکتر = اولویت بالاتر)."""
    if not coop_type:
        return 99
    return COOPERATION_PRIORITY.get(str(coop_type).strip().lower(), 99)


# ==================================================
# مایگریشن: ساخت جداول مطلوبیت‌ها
# ==================================================

def ensure_preferences_tables(db):
    """
    ساخت جداول teaching_preferences و time_preferences در صورت عدم وجود.
    این تابع هیچ تغییری در جداول فعلی نمی‌دهد — کاملاً additive است.
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # جدول teaching_preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teaching_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_course_code TEXT,
                course_name TEXT,
                cooperation_type TEXT,
                expert_group TEXT,
                row_number INTEGER,
                instructor_code TEXT,
                instructor_name TEXT,
                instructor_username TEXT,
                status TEXT DEFAULT 'pending',
                term_code TEXT,
                priority INTEGER DEFAULT 999,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول time_preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS time_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT,
                cooperation_type TEXT,
                end_time TEXT,
                expert_group TEXT,
                row_number INTEGER,
                status INTEGER DEFAULT 1,
                instructor_code TEXT,
                instructor_name TEXT,
                instructor_username TEXT,
                start_time TEXT,
                time_group TEXT,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ایندکس‌ها
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tp_course ON teaching_preferences(unique_course_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tp_instructor ON teaching_preferences(instructor_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tp_status ON teaching_preferences(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_pref_inst ON time_preferences(instructor_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_time_pref_day ON time_preferences(day)")

        # جدول دوره‌های زمانی ثبت مطلوبیت‌ها
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preference_periods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                semester TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                deadline TEXT,
                is_active INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_periods_active ON preference_periods(is_active)")

        conn.commit()
        logger.info("✓ preferences tables ensured (teaching + time + periods)")
    return True


# ==================================================
# CRUD: مطلوبیت‌های تدریس
# ==================================================

def get_all_teaching_preferences(db, term_code=None, instructor_code=None):
    """گرفتن همه مطلوبیت‌های تدریس با فیلتر اختیاری."""
    # اطمینان از وجود جدول
    ensure_preferences_tables(db)
    query = "SELECT * FROM teaching_preferences WHERE 1=1"
    params = []
    if term_code:
        query += " AND term_code = ?"
        params.append(term_code)
    if instructor_code:
        query += " AND instructor_code = ?"
        params.append(instructor_code)
    query += " ORDER BY id DESC"
    rows = db.execute_query(query, tuple(params))
    if rows is None:
        return []
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def create_teaching_preference(db, data: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """ساخت مطلوبیت تدریس — نرمال‌سازی کدها قبل از ذخیره.
    از کانکشن مستقیم sqlite3 استفاده می‌کند تا last_insert_rowid درست کار کند."""
    import sqlite3 as _sqlite3
    # اطمینان از وجود جدول
    ensure_preferences_tables(db)
    # نرمال‌سازی
    unique_code = normalize_code(data.get("unique_course_code", ""))
    instructor_code = normalize_instructor_code(data.get("instructor_code", ""))

    query = """
        INSERT INTO teaching_preferences
            (unique_course_code, course_name, cooperation_type, expert_group,
             row_number, instructor_code, instructor_name, instructor_username,
             status, term_code, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        unique_code,
        data.get("course_name", ""),
        data.get("cooperation_type", ""),
        data.get("expert_group", ""),
        data.get("row_number") or 0,
        instructor_code,
        data.get("instructor_name", ""),
        data.get("instructor_username", ""),
        data.get("status", "pending"),
        data.get("term_code", ""),
        data.get("priority") or 999,
    )
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        pref_id = cursor.lastrowid
        conn.close()
        return pref_id, None
    except Exception as e:
        logger.error(f"create_teaching_preference error: {e}")
        return None, str(e)


def update_teaching_preference(db, pref_id: int, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """ویرایش مطلوبیت تدریس."""
    existing = db.execute_query("SELECT id FROM teaching_preferences WHERE id = ?", (pref_id,))
    if not existing:
        return False, "رکورد پیدا نشد"

    unique_code = normalize_code(data.get("unique_course_code", ""))
    instructor_code = normalize_instructor_code(data.get("instructor_code", ""))

    query = """
        UPDATE teaching_preferences SET
            unique_course_code = ?, course_name = ?, cooperation_type = ?,
            expert_group = ?, row_number = ?, instructor_code = ?,
            instructor_name = ?, instructor_username = ?, status = ?,
            term_code = ?, priority = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """
    params = (
        unique_code, data.get("course_name", ""), data.get("cooperation_type", ""),
        data.get("expert_group", ""), data.get("row_number") or 0,
        instructor_code, data.get("instructor_name", ""),
        data.get("instructor_username", ""), data.get("status", "pending"),
        data.get("term_code", ""), data.get("priority") or 999, pref_id,
    )
    result = db.execute_query(query, params)
    return (result is not None), None


def delete_teaching_preference(db, pref_id: int) -> Tuple[bool, Optional[str]]:
    """حذف مطلوبیت تدریس."""
    import sqlite3 as _sqlite3
    ensure_preferences_tables(db)
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM teaching_preferences WHERE id = ?", (pref_id,))
        if not cursor.fetchone():
            conn.close()
            return False, "رکورد پیدا نشد"
        cursor.execute("DELETE FROM teaching_preferences WHERE id = ?", (pref_id,))
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


# ==================================================
# CRUD: مطلوبیت‌های زمان‌بندی
# ==================================================

def get_all_time_preferences(db, instructor_code=None, day=None):
    """گرفتن همه مطلوبیت‌های زمان‌بندی."""
    # اطمینان از وجود جدول
    ensure_preferences_tables(db)
    query = "SELECT * FROM time_preferences WHERE 1=1"
    params = []
    if instructor_code:
        query += " AND instructor_code = ?"
        params.append(instructor_code)
    if day:
        query += " AND day = ?"
        params.append(day)
    query += " ORDER BY instructor_code, day, priority"
    rows = db.execute_query(query, tuple(params))
    if rows is None:
        return []
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def create_time_preference(db, data: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """ساخت مطلوبیت زمان‌بندی.
    - جلوگیری از ثبت تکراری (همان استاد + روز + بازه)
    - اولویت‌بندی خودکار بر اساس ترتیب زمانی"""
    import sqlite3 as _sqlite3
    # اطمینان از وجود جدول
    ensure_preferences_tables(db)
    start_time = data.get("start_time", "")
    end_time = data.get("end_time", "")
    # تعیین گروه زمانی به‌صورت خودکار
    if not data.get("time_group"):
        period, _ = get_period_for_time(start_time)
        data["time_group"] = period

    instructor_code = normalize_instructor_code(data.get("instructor_code", ""))
    day = data.get("day", "")
    time_group = data.get("time_group", "morning")

    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        cursor = conn.cursor()

        # بررسی تکراری بودن (همان استاد + روز + بازه زمانی)
        existing = cursor.execute(
            "SELECT id FROM time_preferences WHERE instructor_code = ? AND day = ? AND time_group = ?",
            (instructor_code, day, time_group)
        ).fetchone()
        if existing:
            conn.close()
            return None, f"زمان تکراری: این بازه برای {day} - {time_group} قبلاً ثبت شده است."

        # محاسبه اولویت بر اساس ترتیب زمانی
        # تبدیل روز به عدد برای مرتب‌سازی
        DAY_NUMS = {"شنبه": 0, "یکشنبه": 1, "دوشنبه": 2, "سه‌شنبه": 3, "چهارشنبه": 4, "پنجشنبه": 5}
        day_num = DAY_NUMS.get(day, 6)
        PERIOD_ORDER = {"morning": 0, "noon": 1, "afternoon": 2}
        period_order = PERIOD_ORDER.get(time_group, 3)

        # گرفتن همه زمان‌های موجود این استاد
        existing_times = cursor.execute(
            "SELECT id, day, time_group FROM time_preferences WHERE instructor_code = ? ORDER BY id",
            (instructor_code,)
        ).fetchall()

        # محاسبه اولویت جدید: جایگاه زمانی جدید در ترتیب مرتب
        all_slots = []
        for row in existing_times:
            r = dict(row)
            d_num = DAY_NUMS.get(r["day"], 6)
            p_order = PERIOD_ORDER.get(r["time_group"], 3)
            all_slots.append((d_num * 10 + p_order, r["id"]))
        # اضافه کردن زمان جدید
        new_sort_key = day_num * 10 + period_order
        all_slots.append((new_sort_key, None))
        # مرتب‌سازی بر اساس sort_key
        all_slots.sort(key=lambda x: x[0])
        # اولویت = جایگاه در لیست مرتب شده + 1
        priority = 1
        for sort_key, slot_id in all_slots:
            if slot_id is None:
                break
            priority += 1

        query = """
            INSERT INTO time_preferences
                (day, cooperation_type, end_time, expert_group, row_number,
                 status, instructor_code, instructor_name, instructor_username,
                 start_time, time_group, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            day,
            data.get("cooperation_type", ""),
            end_time,
            data.get("expert_group", ""),
            data.get("row_number") or 0,
            1 if data.get("status", True) else 0,
            instructor_code,
            data.get("instructor_name", ""),
            data.get("instructor_username", ""),
            start_time,
            time_group,
            priority,
        )
        cursor.execute(query, params)
        conn.commit()
        pref_id = cursor.lastrowid
        conn.close()
        return pref_id, None
    except Exception as e:
        logger.error(f"create_time_preference error: {e}")
        return None, str(e)


def update_time_preference(db, pref_id: int, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """ویرایش مطلوبیت زمان‌بندی."""
    existing = db.execute_query("SELECT id FROM time_preferences WHERE id = ?", (pref_id,))
    if not existing:
        return False, "رکورد پیدا نشد"

    if not data.get("time_group"):
        period, _ = get_period_for_time(data.get("start_time", ""))
        data["time_group"] = period

    query = """
        UPDATE time_preferences SET
            day = ?, cooperation_type = ?, end_time = ?, expert_group = ?,
            row_number = ?, status = ?, instructor_code = ?,
            instructor_name = ?, instructor_username = ?, start_time = ?,
            time_group = ?, priority = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """
    params = (
        data.get("day", ""), data.get("cooperation_type", ""),
        data.get("end_time", ""), data.get("expert_group", ""),
        data.get("row_number") or 0,
        1 if data.get("status", True) else 0,
        normalize_instructor_code(data.get("instructor_code", "")),
        data.get("instructor_name", ""),
        data.get("instructor_username", ""),
        data.get("start_time", ""),
        data.get("time_group", "morning"),
        data.get("priority") or 0,
        pref_id,
    )
    result = db.execute_query(query, params)
    return (result is not None), None


def delete_time_preference(db, pref_id: int) -> Tuple[bool, Optional[str]]:
    """حذف مطلوبیت زمان‌بندی."""
    import sqlite3 as _sqlite3
    ensure_preferences_tables(db)
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM time_preferences WHERE id = ?", (pref_id,))
        if not cursor.fetchone():
            conn.close()
            return False, "رکورد پیدا نشد"
        cursor.execute("DELETE FROM time_preferences WHERE id = ?", (pref_id,))
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


# ==================================================
# آپلود اکسل — مطلوبیت‌های تدریس
# ==================================================

# نقشه ستون‌های اکسل به فیلد مدل
TEACHING_EXCEL_MAP = {
    "کد یکتا درس": "unique_course_code",
    "نام درس": "course_name",
    "نوع همکاری": "cooperation_type",
    "گروه تخصصی": "expert_group",
    "ردیف": "row_number",
    "کد استاد": "instructor_code",
    "نام استاد": "instructor_name",
    "یوزرنیم استاد": "instructor_username",
    "وضعیت": "status",
    "کد ترم تحصیلی": "term_code",
}


def import_teaching_preferences_excel(db, file_path: str) -> Dict[str, Any]:
    """
    آپلود اکسل مطلوبیت‌های تدریس.
    برمی‌گرداند: {"message": ..., "count": n, "errors": [...]}
    """
    try:
        import pandas as pd
    except ImportError:
        return {"message": "", "count": 0, "errors": ["کتابخانه pandas نصب نیست"]}

    try:
        df = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        return {"message": "", "count": 0, "errors": [f"خطا در خواندن فایل: {e}"]}

    # نرمال‌سازی نام ستون‌ها
    df.columns = [str(c).strip().replace("  ", " ").replace("\u200c", "") for c in df.columns]
    logger.info(f"ستون‌های شناسایی‌شده در فایل مطلوبیت‌های تدریس: {list(df.columns)}")

    # بررسی ستون‌های الزامی
    required = ["نام درس", "نام استاد"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "message": f"ستون‌های ضروری وجود ندارند: {', '.join(missing)}",
            "count": 0,
            "errors": [f"missing columns: {missing}"],
        }

    # نگاشت ستون‌ها
    mapped_data = []
    for idx, row in df.iterrows():
        row_dict = {}
        for fa_name, en_name in TEACHING_EXCEL_MAP.items():
            if fa_name in df.columns:
                val = row[fa_name]
                # مقادیر NaN به None
                if pd.isna(val):
                    val = None
                else:
                    val = str(val).strip()
                    # فلووت صحیح به int
                    if en_name == "row_number" and val and val.replace(".", "").isdigit():
                        try:
                            val = int(float(val))
                        except Exception:
                            pass
                row_dict[en_name] = val
        # بررسی الزامی بودن نام درس و نام استاد
        if not row_dict.get("course_name") or not row_dict.get("instructor_name"):
            # افزودن به لیست خطا بدون قطع عملیات
            row_dict["_error"] = f"ردیف {idx + 2}: نام درس یا نام استاد خالی است"
        # نرمال‌سازی term_code
        if row_dict.get("term_code"):
            row_dict["term_code"] = normalize_term(row_dict["term_code"])
        mapped_data.append(row_dict)

    # ذخیره رکوردها
    success_count = 0
    errors = []
    for row_dict in mapped_data:
        if row_dict.get("_error"):
            errors.append(row_dict["_error"])
            continue
        # نرمال‌سازی کدها
        row_dict["unique_course_code"] = normalize_code(row_dict.get("unique_course_code", ""))
        row_dict["instructor_code"] = normalize_instructor_code(row_dict.get("instructor_code", ""))
        # وضعیت پیش‌فرض
        if not row_dict.get("status"):
            row_dict["status"] = "pending"

        pref_id, err = create_teaching_preference(db, row_dict)
        if err:
            errors.append(f"ردیف {success_count + len(errors) + 1}: {err}")
        else:
            success_count += 1

    if success_count == 0 and errors:
        return {
            "message": "",
            "count": 0,
            "errors": errors[:5],
            "status_code": 400,
        }

    return {
        "message": f"بارگذاری با موفقیت انجام شد. {success_count} رکورد اضافه شد.",
        "count": success_count,
        "errors": errors,
    }


# ==================================================
# آپلود اکسل — مطلوبیت‌های زمان‌بندی
# ==================================================

TIME_EXCEL_MAP = {
    "روز": "day",
    "نوع همکاری": "cooperation_type",
    "زمان پایان": "end_time",
    "گروه تخصصی": "expert_group",
    "ردیف": "row_number",
    "وضعیت": "status",
    "کد استاد": "instructor_code",
    "استاد": "instructor_name",
    "یوزرنیم استاد": "instructor_username",
    "زمان شروع": "start_time",
    "گروه زمانی": "time_group",
    "اولویت": "priority",
}


def import_time_preferences_excel(db, file_path: str, term: str = "mehr") -> Dict[str, Any]:
    """
    آپلود اکسل مطلوبیت‌های زمان‌بندی با اعتبارسنجی اسلات.
    """
    try:
        import pandas as pd
    except ImportError:
        return {"message": "", "count": 0, "errors": ["کتابخانه pandas نصب نیست"]}

    try:
        df = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        return {"message": "", "count": 0, "errors": [f"خطا در خواندن فایل: {e}"]}

    # نرمال‌سازی ستون‌ها
    df.columns = [str(c).strip().replace("  ", " ").replace("\u200c", "") for c in df.columns]
    logger.info(f"ستون‌های شناسایی‌شده در فایل مطلوبیت‌های زمان‌بندی: {list(df.columns)}")

    # ستون‌های الزامی
    required = ["روز", "استاد", "زمان شروع", "زمان پایان"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "message": f"ستون‌های ضروری وجود ندارند: {', '.join(missing)}",
            "count": 0,
            "errors": [f"missing columns: {missing}"],
        }

    # نرمال‌سازی ترم
    term_key = normalize_term(term)

    mapped_data = []
    errors = []
    success_count = 0

    for idx, row in df.iterrows():
        row_dict = {}
        for fa_name, en_name in TIME_EXCEL_MAP.items():
            if fa_name in df.columns:
                val = row[fa_name]
                if pd.isna(val):
                    val = None
                else:
                    val = str(val).strip()
                    if en_name == "row_number" and val and val.replace(".", "").isdigit():
                        try:
                            val = int(float(val))
                        except Exception:
                            pass
                    elif en_name == "priority" and val and val.replace(".", "").isdigit():
                        try:
                            val = int(float(val))
                        except Exception:
                            pass
                row_dict[en_name] = val

        # بررسی روز و نام استاد
        if not row_dict.get("day") or not row_dict.get("instructor_name"):
            errors.append(f"ردیف {idx + 2}: روز یا نام استاد خالی است")
            continue

        # تبدیل status به Boolean
        status_val = row_dict.get("status")
        if isinstance(status_val, str):
            status_val_lower = status_val.strip().lower()
            if status_val_lower in ("true", "1", "yes", "فعال"):
                row_dict["status"] = True
            else:
                row_dict["status"] = False
        elif status_val is None:
            row_dict["status"] = False
        else:
            row_dict["status"] = bool(status_val)

        # اعتبارسنجی اسلات (برای پیش‌فرض 2 واحد)
        start_time = row_dict.get("start_time")
        end_time = row_dict.get("end_time")
        if start_time and end_time:
            try:
                valid = is_valid_slot(start_time, end_time, term=term, units=2)
                if not valid:
                    errors.append(
                        f"ردیف {idx + 2}: زمان {start_time}-{end_time} با اسلات‌های استاندارد ترم {term} برای 2 واحد مطابقت ندارد"
                    )
                    continue
            except Exception:
                # اگر اعتبارسنجی ممکن نبود، رکورد را بپذیر
                pass

        # نرمال‌سازی روز
        day_norm = normalize_day(row_dict.get("day"))
        if day_norm is not None:
            row_dict["day"] = DAY_NAMES_FA.get(day_norm, row_dict.get("day"))

        pref_id, err = create_time_preference(db, row_dict)
        if err:
            errors.append(f"ردیف {idx + 2}: {err}")
        else:
            success_count += 1

    if success_count == 0 and errors:
        return {
            "message": "",
            "count": 0,
            "errors": errors[:5],
            "status_code": 400,
        }

    return {
        "message": f"بارگذاری با موفقیت انجام شد. {success_count} رکورد اضافه شد.",
        "count": success_count,
        "errors": errors,
    }


# ==================================================
# بارگذاری مطلوبیت‌ها برای موتور زمان‌بندی
# ==================================================

def load_instructor_preferences_for_scheduler(db):
    """
    بارگذاری مطلوبیت‌ها برای موتور زمان‌بندی.
    برمی‌گرداند: (teaching_prefs, time_prefs)
      - teaching_prefs: dict[course_code] = [inst_code, ...]  (مرتب بر اساس اولویت)
      - time_prefs: dict[inst_code] = [(day_num, start, end, priority), ...]
    """
    teaching_prefs = {}
    time_prefs = {}

    # مطلوبیت‌های تدریس
    tp_rows = db.execute_query(
        "SELECT * FROM teaching_preferences WHERE unique_course_code IS NOT NULL AND instructor_code IS NOT NULL"
    ) or []
    for r in tp_rows:
        r_dict = dict(r) if not isinstance(r, dict) else r
        course_code = normalize_code(r_dict.get("unique_course_code", ""))
        inst_code = normalize_instructor_code(r_dict.get("instructor_code", ""))
        if not course_code or not inst_code:
            continue
        priority = r_dict.get("priority") or 999
        coop = r_dict.get("cooperation_type", "")
        # کلید مرتب‌سازی: (اولویت صعودی، اولویت همکاری نزولی)
        sort_key = (priority, -get_cooperation_priority(coop))
        if course_code not in teaching_prefs:
            teaching_prefs[course_code] = []
        teaching_prefs[course_code].append((inst_code, sort_key))

    # مرتب‌سازی هر لیست بر اساس sort_key
    for course_code, lst in teaching_prefs.items():
        lst.sort(key=lambda x: x[1])
        teaching_prefs[course_code] = [item[0] for item in lst]

    # مطلوبیت‌های زمان
    time_rows = db.execute_query("SELECT * FROM time_preferences") or []
    for r in time_rows:
        r_dict = dict(r) if not isinstance(r, dict) else r
        inst_code = normalize_instructor_code(r_dict.get("instructor_code", ""))
        if not inst_code:
            continue
        day_norm = normalize_day(r_dict.get("day"))
        if day_norm is None:
            logger.warning(f"روز '{r_dict.get('day')}' برای استاد {inst_code} شناسایی نشد.")
            continue
        start = r_dict.get("start_time")
        end = r_dict.get("end_time")
        priority = r_dict.get("priority") or 0
        if not start or not end:
            continue
        if inst_code not in time_prefs:
            time_prefs[inst_code] = []
        time_prefs[inst_code].append((day_norm, start, end, priority))

    # مرتب‌سازی بر اساس priority
    for inst_code in time_prefs:
        time_prefs[inst_code].sort(key=lambda x: x[3])

    logger.info(f"📚 مطلوبیت تدریس: {len(teaching_prefs)} درس")
    logger.info(f"⏰ مطلوبیت زمان: {len(time_prefs)} استاد")

    return teaching_prefs, time_prefs


# ==================================================
# گزارش تطابق
# ==================================================

def time_to_minutes(t: str) -> int:
    """تبدیل 'HH:MM' به تعداد دقیقه."""
    if not t:
        return 0
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def is_time_slot_match_with_tolerance(start: str, end: str,
                                       pref_start: str, pref_end: str,
                                       tolerance_minutes: int = 60) -> bool:
    """بررسی تطابق بازه با رواداری ±60 دقیقه."""
    s1, e1 = time_to_minutes(start), time_to_minutes(end)
    s2, e2 = time_to_minutes(pref_start), time_to_minutes(pref_end)
    # اگر بازه‌ها با رواداری هم‌پوشانی دارند
    return (s1 <= e2 + tolerance_minutes) and (s2 <= e1 + tolerance_minutes)


def get_match_status(item: Dict[str, Any], teaching_lookup: Dict, time_lookup: Dict) -> str:
    """
    تعیین وضعیت تطابق یک تخصیص.
    برمی‌گرداند: 'full' / 'partial' / 'none' / 'no_preference'
    """
    course_code = normalize_code(item.get("unique_course_code", ""))
    inst_code = normalize_instructor_code(item.get("instructor_code", ""))
    day = item.get("day")
    start = item.get("start_time")
    end = item.get("end_time")

    teach_pref = teaching_lookup.get(course_code, [])
    time_pref = time_lookup.get(inst_code, [])

    if not teach_pref and not time_pref:
        return "no_preference"

    match_count = 0

    # تطابق تدریس
    teach_match = inst_code in teach_pref
    if teach_match:
        match_count += 1

    # تطابق روز
    day_match = False
    time_match = False
    if time_pref:
        day_num = normalize_day(day)
        if day_num is not None:
            for (d, s, e, p) in time_pref:
                if d == day_num:
                    day_match = True
                    if start and end and is_time_slot_match_with_tolerance(start, end, s, e):
                        time_match = True
                        break
    if day_match:
        match_count += 1
    if time_match:
        match_count += 1

    if match_count == 3:
        return "full"
    elif match_count >= 1:
        return "partial"
    else:
        return "none"

# ==================================================
# دوره‌های زمانی ثبت مطلوبیت‌ها
# ==================================================

def get_active_preference_period(db):
    """گرفتن دوره فعال مطلوبیت‌ها."""
    ensure_preferences_tables(db)
    rows = db.execute_query("SELECT * FROM preference_periods WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    if not rows:
        return None
    return dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]


def get_all_preference_periods(db):
    """گرفتن همه دوره‌های مطلوبیت‌ها."""
    ensure_preferences_tables(db)
    rows = db.execute_query("SELECT * FROM preference_periods ORDER BY id DESC")
    if not rows:
        return []
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


def create_preference_period(db, data):
    """ساخت دوره جدید مطلوبیت‌ها."""
    import sqlite3 as _sqlite3
    ensure_preferences_tables(db)
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO preference_periods (name, semester, start_date, end_date, deadline, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            (data.get("name", ""), data.get("semester", ""),
             data.get("start_date", ""), data.get("end_date", ""),
             data.get("deadline", ""), 1 if data.get("is_active") else 0)
        )
        if data.get("is_active"):
            period_id = cursor.lastrowid
            cursor.execute("UPDATE preference_periods SET is_active = 0 WHERE id != ?", (period_id,))
        conn.commit()
        period_id = cursor.lastrowid
        conn.close()
        return period_id, None
    except Exception as e:
        return None, str(e)


def activate_preference_period(db, period_id):
    """فعال‌سازی یک دوره مطلوبیت‌ها."""
    import sqlite3 as _sqlite3
    ensure_preferences_tables(db)
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("UPDATE preference_periods SET is_active = 0")
        cursor.execute("UPDATE preference_periods SET is_active = 1 WHERE id = ?", (period_id,))
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def delete_preference_period(db, period_id):
    """حذف دوره مطلوبیت‌ها."""
    import sqlite3 as _sqlite3
    ensure_preferences_tables(db)
    try:
        conn = _sqlite3.connect(db.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM preference_periods WHERE id = ?", (period_id,))
        conn.commit()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)

