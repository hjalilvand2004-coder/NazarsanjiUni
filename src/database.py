"""
database.py — نسخه ۲.۳.۰
مدیریت دیتابیس SQLite با اسکیمای کامل + Seed خودکار از فایل‌های اکسل پایه.

جداول:
- unique_courses (جدید v2.3): دروس یکتا با کد، عنوان، گروه، ظرفیت
- courses (بهبودیافته v2.3): دروس تفکیکی با کد یکتا، نظری/عملی، ظرفیت
- surveys, course_requests, authorized_users, admin_users, audit_log, login_history, system_settings, notifications
"""

import sqlite3
import os
import sys
import hashlib
import hmac
import secrets
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from src.config import (
    DB_PATH, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD,
    PASSWORD_HASH_ITERATIONS,
    CHANNEL_BOT, CHANNEL_MINIAPP, CHANNEL_WEBSITE,
    YEKTA_COURSES_FILE, DETAIL_COURSES_FILE,
)

if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ==================================================
# Password Hashing
# ==================================================

def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS,
    )
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) != 3 or parts[0] != "pbkdf2":
            return False
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS,
        )
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


class Database:

    def __init__(self):
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.db_path = DB_PATH
        self.init_database()
        self.seed_admin_if_empty()
        self.seed_courses_from_excel()
        # 注意: در v2.4 نظرسنجی بهمن 1405 به‌صورت خودکار ساخته نمی‌شود.
        # ادمین باید از پنل /admin/surveys اولین نظرسنجی را بسازد و فعال کند.

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def execute_query(self, query: str, params: tuple = ()):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                if query.strip().upper().startswith("SELECT"):
                    return cursor.fetchall()
                conn.commit()
                return True
        except Exception as e:
            print(f"❌ DB execute_query error: {e}")
            return None

    # --------------------------------------------------
    # Schema
    # --------------------------------------------------
    def init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # جدول جدید: دروس یکتا (v2.3.0)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS unique_courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unique_code INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                course_group TEXT,
                capacity_estimate INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # جدول دروس تفکیکی (بهبودیافته v2.3.0)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                section TEXT NOT NULL,
                row_number INTEGER,
                course_title TEXT NOT NULL,
                credits TEXT,
                theory_credits INTEGER,
                practical_credits INTEGER,
                prerequisite TEXT,
                corequisite TEXT,
                year INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                type_coures TEXT,
                unique_code INTEGER REFERENCES unique_courses(unique_code),
                capacity_estimate INTEGER DEFAULT 30,
                survey_id INTEGER REFERENCES surveys(id)
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS authorized_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                display_phone TEXT NOT NULL,
                normalized_phone TEXT NOT NULL UNIQUE,
                student_number TEXT UNIQUE,
                student_type TEXT CHECK(student_type IN('پیوسته','ناپیوسته')),
                role TEXT DEFAULT 'user' CHECK(role IN ('user','admin')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bale_id INTEGER,
                last_seen TIMESTAMP,
                is_blocked INTEGER DEFAULT 0,
                first_channel TEXT,
                password_hash TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS course_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES authorized_users(id),
                course_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                id_courses INTEGER,
                survey_id INTEGER REFERENCES surveys(id),
                channel TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES authorized_users(id),
                title TEXT NOT NULL,
                body TEXT,
                level TEXT DEFAULT 'info',
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                email TEXT,
                role TEXT DEFAULT 'admin' CHECK(role IN ('admin','super_admin','viewer')),
                is_active INTEGER DEFAULT 1,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER REFERENCES admin_users(id),
                admin_username TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                description TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES admin_users(id)
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                semester TEXT NOT NULL,
                year INTEGER NOT NULL,
                start_date TEXT,
                end_date TEXT,
                deadline TEXT,
                is_active INTEGER DEFAULT 0,
                created_by INTEGER REFERENCES admin_users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES authorized_users(id),
                channel TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # مایگریشن: افزودن ستون‌های جدید به courses موجود
            try: cursor.execute("ALTER TABLE courses ADD COLUMN unique_code INTEGER")
            except Exception: pass
            try: cursor.execute("ALTER TABLE courses ADD COLUMN theory_credits INTEGER")
            except Exception: pass
            try: cursor.execute("ALTER TABLE courses ADD COLUMN practical_credits INTEGER")
            except Exception: pass
            try: cursor.execute("ALTER TABLE courses ADD COLUMN capacity_estimate INTEGER DEFAULT 30")
            except Exception: pass
            try: cursor.execute("ALTER TABLE authorized_users ADD COLUMN first_channel TEXT")
            except Exception: pass
            try: cursor.execute("ALTER TABLE authorized_users ADD COLUMN password_hash TEXT")
            except Exception: pass
            try: cursor.execute("ALTER TABLE course_requests ADD COLUMN survey_id INTEGER")
            except Exception: pass
            try: cursor.execute("ALTER TABLE course_requests ADD COLUMN channel TEXT")
            except Exception: pass

            # ایندکس‌ها
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_unique_courses_code ON unique_courses(unique_code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_unique_courses_group ON unique_courses(course_group)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_unique_code ON courses(unique_code)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_year_type ON courses(year, type_coures)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_bale_id ON authorized_users(bale_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_phone ON authorized_users(normalized_phone)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_user ON course_requests(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_course ON course_requests(id_courses)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_survey ON course_requests(survey_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_admin ON audit_log(admin_id, created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_surveys_active ON surveys(is_active)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_history_user ON login_history(user_id, created_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_history_channel ON login_history(channel, created_at)")
            except Exception:
                pass

            conn.commit()

    # --------------------------------------------------
    # Seed از فایل‌های اکسل پایه (v2.3.0)
    # --------------------------------------------------
    def seed_courses_from_excel(self):
        """اگر جدول دروس خالی است، از فایل‌های اکسل پایه پر شود."""
        rows = self.execute_query("SELECT COUNT(*) AS c FROM unique_courses")
        if not rows or rows[0]["c"] > 0:
            return  # قبلاً پر شده

        try:
            import openpyxl
        except ImportError:
            print("⚠️ openpyxl نصب نیست — Seed اکسل انجام نشد")
            return

        # ۱) خواندن دروس یکتا
        yekta_count = 0
        if os.path.exists(YEKTA_COURSES_FILE):
            try:
                wb = openpyxl.load_workbook(YEKTA_COURSES_FILE, data_only=True)
                ws = wb[wb.sheetnames[0]]
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i == 0:
                        continue  # header
                    if not row or not row[0]:
                        continue
                    unique_code = int(row[0])
                    title = str(row[1] or "").strip()
                    is_active = int(row[2]) if row[2] is not None else 1
                    course_group = str(row[3] or "").strip() if len(row) > 3 else None
                    capacity = int(row[4]) if len(row) > 4 and row[4] else 30

                    self.execute_query(
                        """INSERT OR IGNORE INTO unique_courses
                           (unique_code, title, is_active, course_group, capacity_estimate)
                           VALUES (?, ?, ?, ?, ?)""",
                        (unique_code, title, is_active, course_group, capacity)
                    )
                    yekta_count += 1
                print(f"✅ Seeded {yekta_count} unique courses from {os.path.basename(YEKTA_COURSES_FILE)}")
            except Exception as e:
                print(f"❌ Error reading Yekta file: {e}")
        else:
            print(f"⚠️ File not found: {YEKTA_COURSES_FILE}")

        # ۲) خواندن دروس تفکیکی
        detail_count = 0
        if os.path.exists(DETAIL_COURSES_FILE):
            try:
                wb = openpyxl.load_workbook(DETAIL_COURSES_FILE, data_only=True)
                ws = wb[wb.sheetnames[0]]
                # ستون‌ها: id, نوع درس, row_number, عنوان درس در مقطع ارایه, کد یکتا,
                # عنوان درس یکتا, نظری, عملی, prerequisite, corequisite, year, is_active, type_coures, نوع درس3
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i == 0:
                        continue  # header
                    if not row or not row[3]:
                        continue
                    section_label = str(row[1] or "").strip()      # نوع درس (پایه/اصلی/...)
                    try:
                        row_number = int(row[2]) if row[2] is not None else 0
                    except (ValueError, TypeError):
                        row_number = 0
                    course_title = str(row[3] or "").strip()       # عنوان درس در مقطع
                    # unique_code ممکن است عدد یا '-' باشد
                    try:
                        unique_code = int(row[4]) if row[4] is not None else None
                    except (ValueError, TypeError):
                        unique_code = None
                    # theory_credits (نظری)
                    try:
                        theory = int(row[6]) if row[6] is not None else None
                    except (ValueError, TypeError):
                        theory = None
                    # practical_credits (عملی)
                    try:
                        practical = int(row[7]) if row[7] is not None else None
                    except (ValueError, TypeError):
                        practical = None
                    prerequisite = str(row[8] or "-").strip() if len(row) > 8 else "-"
                    corequisite = str(row[9] or "-").strip() if len(row) > 9 else "-"
                    # year ممکن است عدد یا رشته باشد
                    try:
                        year = int(row[10]) if row[10] is not None else 1394
                    except (ValueError, TypeError):
                        year = 1394
                    try:
                        is_active = int(row[11]) if row[11] is not None else 1
                    except (ValueError, TypeError):
                        is_active = 1
                    type_coures = str(row[12] or "").strip() if len(row) > 12 else "پیوسته"
                    section_code = str(row[13] or "basic").strip() if len(row) > 13 else "basic"

                    credits = str(theory) if theory else ""
                    if practical:
                        credits += f"+{practical}"

                    self.execute_query(
                        """INSERT INTO courses
                           (section, row_number, course_title, credits,
                            theory_credits, practical_credits, prerequisite, corequisite,
                            year, is_active, type_coures, unique_code, capacity_estimate)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (section_code, row_number, course_title, credits,
                         theory, practical, prerequisite, corequisite,
                         year, is_active, type_coures, unique_code, 30)
                    )
                    detail_count += 1
                print(f"✅ Seeded {detail_count} detail courses from {os.path.basename(DETAIL_COURSES_FILE)}")
            except Exception as e:
                print(f"❌ Error reading Detail file: {e}")
        else:
            print(f"⚠️ File not found: {DETAIL_COURSES_FILE}")

    # --------------------------------------------------
    # Seed Admin User
    # --------------------------------------------------
    def seed_admin_if_empty(self):
        rows = self.execute_query("SELECT COUNT(*) AS c FROM admin_users")
        if rows and rows[0]["c"] > 0:
            return
        self.execute_query(
            """INSERT INTO admin_users (username, password_hash, full_name, email, role, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD),
             "مدیر سامانه", "admin@example.com", "super_admin")
        )
        print(f"✅ Default admin: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}")

    # --------------------------------------------------
    # در v2.4: نظرسنجی پیش‌فرض ساخته نمی‌شود — ادمین خودش می‌سازد
    # --------------------------------------------------
    def has_any_survey(self):
        """آیا هیچ نظرسنجی در سامانه وجود دارد؟"""
        rows = self.execute_query("SELECT COUNT(*) AS c FROM surveys")
        return bool(rows and rows[0]["c"] > 0)

    # --------------------------------------------------
    # Unique Courses (دروس یکتا) — مدیریت
    # --------------------------------------------------
    def get_all_unique_courses(self, only_active=False, search=None):
        query = "SELECT * FROM unique_courses"
        params = []
        conditions = []
        if only_active:
            conditions.append("is_active = 1")
        if search:
            conditions.append("(title LIKE ? OR course_group LIKE ? OR CAST(unique_code AS TEXT) LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY course_group, unique_code"
        rows = self.execute_query(query, tuple(params))
        return [dict(r) for r in rows] if rows else []

    def get_unique_course_by_code(self, code):
        rows = self.execute_query(
            "SELECT * FROM unique_courses WHERE unique_code = ?", (code,)
        )
        return dict(rows[0]) if rows else None

    def add_unique_course(self, unique_code, title, is_active=1, course_group="", capacity_estimate=30):
        try:
            self.execute_query(
                """INSERT INTO unique_courses (unique_code, title, is_active, course_group, capacity_estimate)
                   VALUES (?, ?, ?, ?, ?)""",
                (int(unique_code), title.strip(), 1 if is_active else 0,
                 course_group, int(capacity_estimate))
            )
            return True
        except Exception as e:
            print(f"❌ add_unique_course error: {e}")
            return False

    def update_unique_course(self, code, title=None, is_active=None, course_group=None, capacity_estimate=None):
        sets = []
        params = []
        if title is not None:
            sets.append("title = ?"); params.append(title)
        if is_active is not None:
            sets.append("is_active = ?"); params.append(1 if is_active else 0)
        if course_group is not None:
            sets.append("course_group = ?"); params.append(course_group)
        if capacity_estimate is not None:
            sets.append("capacity_estimate = ?"); params.append(int(capacity_estimate))
        if not sets:
            return False
        sets.append("updated_at = ?"); params.append(datetime.utcnow())
        params.append(code)
        self.execute_query(
            f"UPDATE unique_courses SET {', '.join(sets)} WHERE unique_code = ?",
            tuple(params)
        )
        return True

    def delete_unique_course(self, code):
        # بررسی اینکه آیا درس تفکیکی به آن وابسته است
        cnt = self.execute_query(
            "SELECT COUNT(*) AS c FROM courses WHERE unique_code = ?", (code,)
        )
        if cnt and cnt[0]["c"] > 0:
            return False
        self.execute_query("DELETE FROM unique_courses WHERE unique_code = ?", (code,))
        return True

    # --------------------------------------------------
    # Courses (دروس تفکیکی) — مدیریت
    # --------------------------------------------------
    def get_course_by_id(self, course_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM courses WHERE id=?", (course_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_courses(self, only_active=True, year=None, type_coures=None, section=None):
        query = "SELECT * FROM courses"
        conditions = []
        params = []
        if only_active:
            conditions.append("is_active = 1")
        if year:
            conditions.append("year = ?"); params.append(int(year))
        if type_coures:
            conditions.append("type_coures = ?"); params.append(type_coures)
        if section:
            conditions.append("section = ?"); params.append(section)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY year DESC, type_coures, row_number ASC, id ASC"
        rows = self.execute_query(query, tuple(params))
        return [dict(row) for row in rows] if rows else []

    def add_course(self, section, row_number, course_title, credits, prerequisite, corequisite,
                   year, type_coures, unique_code=None, theory_credits=None,
                   practical_credits=None, capacity_estimate=30):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO courses (section, row_number, course_title, credits,
                                     theory_credits, practical_credits, prerequisite, corequisite,
                                     year, is_active, type_coures, unique_code, capacity_estimate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """, (section, int(row_number or 0), course_title, credits,
                      theory_credits, practical_credits, prerequisite, corequisite,
                      int(year), type_coures, unique_code, int(capacity_estimate or 30)))
            return True
        except Exception as e:
            print(f"❌ add_course error: {e}")
            return False

    def update_course(self, course_id, course_title, section, credits, prerequisite, year, type_coures,
                      unique_code=None, theory_credits=None, practical_credits=None,
                      capacity_estimate=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE courses
                    SET course_title = ?, section = ?, credits = ?, prerequisite = ?,
                        year = ?, type_coures = ?, unique_code = ?,
                        theory_credits = ?, practical_credits = ?, capacity_estimate = ?
                    WHERE id = ?
                """, (course_title, section, credits, prerequisite, int(year), type_coures,
                      unique_code, theory_credits, practical_credits,
                      int(capacity_estimate or 30), course_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error updating course: {e}")
            return False

    def delete_course(self, course_id):
        self.execute_query("DELETE FROM courses WHERE id = ?", (course_id,))

    # --------------------------------------------------
    # Surveys
    # --------------------------------------------------
    def get_active_survey(self):
        rows = self.execute_query(
            "SELECT * FROM surveys WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        )
        return dict(rows[0]) if rows else None

    def get_survey_by_id(self, survey_id):
        rows = self.execute_query("SELECT * FROM surveys WHERE id = ?", (survey_id,))
        return dict(rows[0]) if rows else None

    def get_all_surveys(self):
        rows = self.execute_query("SELECT * FROM surveys ORDER BY created_at DESC")
        return [dict(r) for r in rows] if rows else []

    def create_survey(self, name, semester, year, start_date=None, end_date=None,
                      deadline=None, created_by=None):
        self.execute_query(
            """INSERT INTO surveys (name, semester, year, start_date, end_date, deadline, is_active, created_by)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
            (name, semester, int(year), start_date, end_date, deadline, created_by)
        )

    def activate_survey(self, survey_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE surveys SET is_active = 0")
            cursor.execute("UPDATE surveys SET is_active = 1 WHERE id = ?", (survey_id,))
            conn.commit()

    def close_survey(self, survey_id):
        self.execute_query(
            "UPDATE surveys SET is_active = 0, closed_at = ? WHERE id = ?",
            (datetime.utcnow(), survey_id)
        )

    def delete_survey(self, survey_id):
        cnt = self.execute_query(
            "SELECT COUNT(*) AS c FROM course_requests WHERE survey_id = ?", (survey_id,)
        )
        if cnt and cnt[0]["c"] > 0:
            return False
        self.execute_query("DELETE FROM surveys WHERE id = ?", (survey_id,))
        return True

    # --------------------------------------------------
    # Login History
    # --------------------------------------------------
    def record_login(self, user_id, channel, ip_address=None, user_agent=None):
        self.execute_query(
            """INSERT INTO login_history (user_id, channel, ip_address, user_agent)
               VALUES (?, ?, ?, ?)""",
            (user_id, channel, ip_address, user_agent)
        )
        if user_id:
            rows = self.execute_query(
                "SELECT first_channel FROM authorized_users WHERE id = ?", (user_id,)
            )
            if rows and not rows[0]["first_channel"]:
                self.execute_query(
                    "UPDATE authorized_users SET first_channel = ? WHERE id = ?",
                    (channel, user_id)
                )

    def get_user_login_history(self, user_id, limit=20):
        rows = self.execute_query(
            "SELECT * FROM login_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return [dict(r) for r in rows] if rows else []

    def get_channel_stats(self):
        rows = self.execute_query("""
            SELECT COALESCE(u.first_channel, 'unknown') AS channel,
                   COUNT(DISTINCT u.id) AS user_count
            FROM authorized_users u
            GROUP BY COALESCE(u.first_channel, 'unknown')
        """) or []
        result = []
        for r in rows:
            ch = r["channel"]
            cnt = self.execute_query(
                "SELECT COUNT(*) AS c FROM login_history WHERE channel = ?", (ch,)
            )
            result.append({
                "channel": ch, "user_count": r["user_count"],
                "login_count": cnt[0]["c"] if cnt else 0
            })
        return result

    def get_login_timeline(self, days=14):
        rows = self.execute_query(
            """SELECT DATE(created_at) AS day, channel, COUNT(*) AS cnt
               FROM login_history
               WHERE created_at >= datetime('now', ?)
               GROUP BY DATE(created_at), channel
               ORDER BY day ASC""",
            (f"-{days} days",)
        )
        return [dict(r) for r in rows] if rows else []

    def get_recent_logins(self, limit=20):
        rows = self.execute_query(
            """SELECT lh.id, lh.channel, lh.ip_address, lh.created_at,
                      u.name, u.student_number, u.display_phone
               FROM login_history lh
               LEFT JOIN authorized_users u ON lh.user_id = u.id
               ORDER BY lh.created_at DESC LIMIT ?""",
            (limit,)
        )
        return [dict(r) for r in rows] if rows else []

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def normalize_phone(self, phone):
        phone = ''.join(filter(str.isdigit, str(phone)))
        if phone.startswith('0') and len(phone) == 11: return '98' + phone[1:]
        if phone.startswith('9') and len(phone) == 10: return '98' + phone
        if phone.startswith('98') and len(phone) == 12: return phone
        return phone

    def validate_student_number(self, student_number):
        student_number = ''.join(filter(str.isdigit, str(student_number)))
        if len(student_number) not in (9, 14):
            return False, "شماره دانشجویی باید ۹ یا ۱۴ رقم باشد."
        if student_number == "000000000":
            admin_count = self.count_admins()
            if admin_count >= 2: return False, "حداکثر دو ادمین مجاز است."
            return True, "admin"
        valid_prefix2 = ("94", "95", "96", "97", "98", "99")
        valid_prefix3 = ("400", "401", "402", "403", "404", "405")
        if student_number.startswith(valid_prefix2) or student_number.startswith(valid_prefix3):
            return True, "user"
        return False, "شماره دانشجویی معتبر نیست."

    def get_student_year(self, student_number):
        if not student_number: return None
        sn = ''.join(filter(str.isdigit, str(student_number)))
        p2, p3 = sn[:2], sn[:3]
        if p2 in ("94", "95", "96", "97", "98", "99") or p3 in ("400", "401", "402"):
            return 1394
        if p3 in ("403", "404", "405"):
            return 1403
        return None

    def user_exists(self, phone, student_number):
        normalized_phone = self.normalize_phone(phone)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM authorized_users
                WHERE normalized_phone = ? OR student_number = ?
            """, (normalized_phone, student_number))
            return cursor.fetchone() is not None

    def count_admins(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM authorized_users WHERE role='admin'")
            row = cursor.fetchone()
            return row["count"] if row else 0

    # --------------------------------------------------
    # User Management
    # --------------------------------------------------
    def add_authorized_user(self, name, phone, student_number, student_type, role,
                            first_channel=None, password_hash=None):
        normalized_phone = self.normalize_phone(phone)
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO authorized_users
                (name, display_phone, normalized_phone, student_number, student_type, role, first_channel, password_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (name.strip(), str(phone).strip(), normalized_phone, student_number,
                      student_type, role, first_channel, password_hash))
            return True
        except Exception as e:
            print("❌ add_authorized_user error:", e)
            return False

    def is_user_authorized(self, phone):
        normalized_phone = self.normalize_phone(phone)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authorized_users WHERE normalized_phone=?", (normalized_phone,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_bale_id(self, bale_id):
        if not bale_id: return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authorized_users WHERE bale_id = ?", (bale_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_user_by_student_number(self, sn):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM authorized_users WHERE student_number = ?", (sn,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def link_bale_id(self, user_id, bale_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE authorized_users SET bale_id = ?, last_seen = ? WHERE id = ?",
                    (bale_id, datetime.utcnow(), user_id)
                )
                conn.commit()
            return True
        except Exception as e:
            print("❌ link_bale_id error:", e)
            return False

    def update_last_seen(self, user_id):
        self.execute_query(
            "UPDATE authorized_users SET last_seen = ? WHERE id = ?",
            (datetime.utcnow(), user_id)
        )

    def set_user_password(self, user_id, password):
        self.execute_query(
            "UPDATE authorized_users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id)
        )

    def verify_user_password(self, user, password):
        if not user or not user.get("password_hash"): return False
        return verify_password(password, user["password_hash"])

    def block_user(self, user_id, blocked=True):
        self.execute_query(
            "UPDATE authorized_users SET is_blocked = ? WHERE id = ?",
            (1 if blocked else 0, user_id)
        )

    def get_all_users(self, limit=100, offset=0, search=None):
        query = "SELECT * FROM authorized_users"
        params = []
        if search:
            query += " WHERE name LIKE ? OR student_number LIKE ? OR display_phone LIKE ?"
            like = f"%{search}%"
            params.extend([like, like, like])
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.execute_query(query, tuple(params))
        return [dict(r) for r in rows] if rows else []

    def count_all_users(self, search=None):
        query = "SELECT COUNT(*) AS c FROM authorized_users"
        params = []
        if search:
            query += " WHERE name LIKE ? OR student_number LIKE ? OR display_phone LIKE ?"
            like = f"%{search}%"
            params = [like, like, like]
        rows = self.execute_query(query, tuple(params))
        return rows[0]["c"] if rows else 0

    # --------------------------------------------------
    # Participation Stats
    # --------------------------------------------------
    def get_participation_stats(self):
        return self.execute_query("""
            SELECT u.student_type, CASE
                WHEN substr(u.student_number,1,2) IN ('94','95','96','97','98','99')
                     OR substr(u.student_number,1,3) IN ('400','401','402') THEN 1394
                WHEN substr(u.student_number,1,3) IN ('403','404','405') THEN 1403
                ELSE -1
            END AS year_group, COUNT(DISTINCT u.id) AS participant_count
            FROM authorized_users u
            JOIN course_requests cr ON cr.user_id = u.id
            WHERE u.role = 'user'
            GROUP BY student_type, year_group
            ORDER BY year_group DESC, student_type
        """)

    # --------------------------------------------------
    # Course Requests
    # --------------------------------------------------
    def add_course_request(self, user_id, course_name, id_courses=None, survey_id=None, channel=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO course_requests (user_id, course_name, id_courses, survey_id, channel)
                VALUES (?, ?, ?, ?, ?)
                """, (user_id, str(course_name).strip(), id_courses, survey_id, channel))
            return True
        except Exception as e:
            print("❌ add_course_request error:", e)
            return False

    def add_user_course(self, user_id, course_id, survey_id=None, channel=None):
        course = self.get_course_by_id(course_id)
        if not course: return False
        return self.add_course_request(
            user_id, course["course_title"], course_id, survey_id, channel
        )

    def has_user_submitted_courses(self, user_id, survey_id=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if survey_id:
                cursor.execute(
                    "SELECT 1 FROM course_requests WHERE user_id = ? AND survey_id = ? LIMIT 1",
                    (user_id, survey_id))
            else:
                cursor.execute(
                    "SELECT 1 FROM course_requests WHERE user_id = ? LIMIT 1", (user_id,))
            return cursor.fetchone() is not None

    def get_user_requests(self, user_id):
        rows = self.execute_query(
            """SELECT cr.*, c.course_title, c.credits, c.section, c.unique_code
               FROM course_requests cr
               LEFT JOIN courses c ON cr.id_courses = c.id
               WHERE cr.user_id = ?
               ORDER BY cr.created_at DESC""",
            (user_id,))
        return [dict(r) for r in rows] if rows else []

    def remove_user_course(self, user_id, course_id):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM course_requests WHERE user_id = ? AND id_courses = ?",
                    (user_id, course_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ remove_user_course error: {e}")
            return False

    # --------------------------------------------------
    # Admin Users
    # --------------------------------------------------
    def get_admin_by_username(self, username):
        rows = self.execute_query(
            "SELECT * FROM admin_users WHERE username = ? AND is_active = 1", (username,))
        return dict(rows[0]) if rows else None

    def get_admin_by_id(self, admin_id):
        rows = self.execute_query("SELECT * FROM admin_users WHERE id = ?", (admin_id,))
        return dict(rows[0]) if rows else None

    def get_all_admins(self):
        rows = self.execute_query(
            "SELECT id, username, full_name, email, role, is_active, last_login, created_at FROM admin_users ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows] if rows else []

    def create_admin(self, username, password, full_name="", email="", role="admin"):
        try:
            self.execute_query(
                """INSERT INTO admin_users (username, password_hash, full_name, email, role, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (username, hash_password(password), full_name, email, role))
            return True
        except Exception as e:
            print(f"❌ create_admin error: {e}")
            return False

    def update_admin_password(self, admin_id, new_password):
        self.execute_query(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), admin_id))

    def update_admin_profile(self, admin_id, full_name=None, email=None):
        if full_name is not None:
            self.execute_query("UPDATE admin_users SET full_name = ? WHERE id = ?", (full_name, admin_id))
        if email is not None:
            self.execute_query("UPDATE admin_users SET email = ? WHERE id = ?", (email, admin_id))

    def toggle_admin_active(self, admin_id):
        rows = self.execute_query("SELECT is_active FROM admin_users WHERE id = ?", (admin_id,))
        if not rows: return
        new_val = 0 if rows[0]["is_active"] else 1
        self.execute_query("UPDATE admin_users SET is_active = ? WHERE id = ?", (new_val, admin_id))

    def update_admin_last_login(self, admin_id):
        self.execute_query(
            "UPDATE admin_users SET last_login = ? WHERE id = ?",
            (datetime.utcnow(), admin_id))

    def delete_admin(self, admin_id):
        rows = self.execute_query(
            "SELECT COUNT(*) AS c FROM admin_users WHERE role = 'super_admin' AND is_active = 1")
        admin = self.get_admin_by_id(admin_id)
        if admin and admin["role"] == "super_admin" and rows and rows[0]["c"] <= 1:
            return False
        self.execute_query("DELETE FROM admin_users WHERE id = ?", (admin_id,))
        return True

    # --------------------------------------------------
    # Audit Log
    # --------------------------------------------------
    def add_audit_log(self, admin_id, admin_username, action, target_type=None,
                      target_id=None, description=None, ip_address=None):
        self.execute_query(
            """INSERT INTO audit_log
               (admin_id, admin_username, action, target_type, target_id, description, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (admin_id, admin_username, action, target_type,
             str(target_id) if target_id else None, description, ip_address))

    def get_audit_logs(self, limit=100, offset=0, action=None):
        query = "SELECT * FROM audit_log"
        params = []
        if action:
            query += " WHERE action = ?"; params.append(action)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.execute_query(query, tuple(params))
        return [dict(r) for r in rows] if rows else []

    # --------------------------------------------------
    # System Settings
    # --------------------------------------------------
    def get_setting(self, key, default=None):
        rows = self.execute_query("SELECT value FROM system_settings WHERE key = ?", (key,))
        if rows and rows[0]["value"] is not None: return rows[0]["value"]
        return default

    def set_setting(self, key, value, admin_id=None):
        self.execute_query(
            """INSERT INTO system_settings (key, value, updated_at, updated_by)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?, updated_by = ?""",
            (key, value, datetime.utcnow(), admin_id, value, datetime.utcnow(), admin_id))

    # --------------------------------------------------
    # Notifications
    # --------------------------------------------------
    def add_notification(self, user_id, title, body, level="info"):
        self.execute_query(
            "INSERT INTO notifications (user_id, title, body, level) VALUES (?, ?, ?, ?)",
            (user_id, title, body, level))

    def get_user_notifications(self, user_id, limit=20):
        rows = self.execute_query(
            "SELECT * FROM notifications WHERE (user_id IS NULL OR user_id = ?) ORDER BY created_at DESC LIMIT ?",
            (user_id, limit))
        return [dict(r) for r in rows] if rows else []

    def mark_notification_read(self, notif_id):
        self.execute_query("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))

    # --------------------------------------------------
    # Analytics
    # --------------------------------------------------
    def get_daily_requests(self, days=30):
        rows = self.execute_query(
            """SELECT DATE(created_at) AS day, COUNT(*) AS cnt
               FROM course_requests WHERE created_at >= datetime('now', ?)
               GROUP BY DATE(created_at) ORDER BY day ASC""",
            (f"-{days} days",))
        return [dict(r) for r in rows] if rows else []

    def get_top_courses(self, limit=20):
        rows = self.execute_query(
            """SELECT c.course_title AS title, c.credits, c.section, c.year, c.unique_code,
                      COUNT(*) AS cnt, COUNT(DISTINCT cr.user_id) AS unique_users
               FROM course_requests cr
               JOIN courses c ON cr.id_courses = c.id
               GROUP BY c.id ORDER BY cnt DESC LIMIT ?""",
            (limit,))
        return [dict(r) for r in rows] if rows else []

    def get_section_distribution(self):
        rows = self.execute_query("""
            SELECT c.section, COUNT(*) AS cnt
            FROM course_requests cr
            JOIN courses c ON cr.id_courses = c.id
            GROUP BY c.section ORDER BY cnt DESC
        """)
        return [dict(r) for r in rows] if rows else []

    def get_student_type_distribution(self):
        rows = self.execute_query("""
            SELECT u.student_type, COUNT(DISTINCT u.id) AS cnt
            FROM authorized_users u
            JOIN course_requests cr ON cr.user_id = u.id
            WHERE u.role = 'user'
            GROUP BY u.student_type
        """)
        return [dict(r) for r in rows] if rows else []

    def get_year_distribution(self):
        rows = self.execute_query("""
            SELECT CASE
                WHEN substr(u.student_number,1,2) IN ('94','95','96','97','98','99')
                     OR substr(u.student_number,1,3) IN ('400','401','402') THEN 1394
                WHEN substr(u.student_number,1,3) IN ('403','404','405') THEN 1403
                ELSE 0
            END AS year_group, COUNT(DISTINCT u.id) AS cnt
            FROM authorized_users u
            JOIN course_requests cr ON cr.user_id = u.id
            WHERE u.role = 'user'
            GROUP BY year_group
        """)
        return [dict(r) for r in rows] if rows else []

    def get_recent_activity(self, limit=20):
        rows = self.execute_query(
            """SELECT cr.id, cr.created_at, u.name, u.student_number,
                      c.course_title, c.section, cr.channel
               FROM course_requests cr
               JOIN authorized_users u ON cr.user_id = u.id
               LEFT JOIN courses c ON cr.id_courses = c.id
               ORDER BY cr.created_at DESC LIMIT ?""",
            (limit,))
        return [dict(r) for r in rows] if rows else []

    # --------------------------------------------------
    # آمار دروس پایه (v2.3.0)
    # --------------------------------------------------
    def get_course_groups_stats(self):
        """آمار دروس یکتا بر اساس گروه"""
        rows = self.execute_query("""
            SELECT course_group, COUNT(*) AS total,
                   SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active
            FROM unique_courses
            GROUP BY course_group
            ORDER BY total DESC
        """)
        return [dict(r) for r in rows] if rows else []

    def get_year_courses_stats(self):
        """تعداد دروس تفکیکی بر اساس سال"""
        rows = self.execute_query("""
            SELECT year, type_coures, COUNT(*) AS cnt
            FROM courses
            WHERE is_active = 1
            GROUP BY year, type_coures
            ORDER BY year DESC, type_coures
        """)
        return [dict(r) for r in rows] if rows else []
