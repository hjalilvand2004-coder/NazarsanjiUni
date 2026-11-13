"""
website.py — نسخه ۲.۲.۰
وب‌سایت مستقل + پنل ادمین کامل + ثبت‌نام دانشجو
سرور: http://188.212.96.235:8080

مسیرهای عمومی:
  /              صفحه اصلی
  /dashboard     داشبورد زنده عمومی
  /courses       فهرست دروس
  /about         درباره
  /register      ثبت‌نام دانشجو
  /login         ورود دانشجو
  /logout        خروج دانشجو
  /student       داشبورد دانشجو (پس از لاگین)
  /api/public/*  APIهای عمومی

مسیرهای ادمین:
  /admin/login, /admin/logout
  /admin                       داشبورد اصلی
  /admin/users                مدیریت کاربران + تاریخچه ورود + کانال
  /admin/courses               مدیریت دروس
  /admin/reports               گزارش‌ها و نمودارها
  /admin/surveys               مدیریت نظرسنجی‌ها (فعال‌سازی/غیرفعال‌سازی) — جدید
  /admin/surveys/add           ساخت نظرسنجی جدید — جدید
  /admin/surveys/<id>/activate فعال‌سازی نظرسنجی — جدید
  /admin/surveys/<id>/close    بستن نظرسنجی — جدید
  /admin/surveys/<id>/delete   حذف نظرسنجی — جدید
  /admin/login-history         تاریخچه ورود کاربران — جدید
  /admin/audit-log             لاگ عملیات
  /admin/settings              تنظیمات
  /admin/admins                مدیریت ادمین‌ها
  /admin/profile               پروفایل ادمین
"""

import io
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, make_response,
    send_from_directory, redirect, url_for, session, flash, g
)

from src.config import (
    DB_PATH, MAX_COURSES_PER_USER, WEB_APP_URL,
    APP_VERSION, WEBSITE_URL, APP_RELEASE_DATE,
    SECRET_KEY, ADMIN_SESSION_TTL, STUDENT_SESSION_TTL,
    DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD,
    CHANNEL_BOT, CHANNEL_MINIAPP, CHANNEL_WEBSITE, CHANNEL_LABELS,
    MOBILE_APP_URL, MOBILE_APP_NAME, MOBILE_APP_VERSION, WEBSITE_PORT,
    COMPANY_NAME, COMPANY_URL,
)
from src.database import Database, hash_password, verify_password
from src import helpers

# ===== [v3.7.0] ورود یکپارچه (SSO) =====
try:
    import sso as sso_module
    SSO_AVAILABLE = True
except Exception as _sso_err:
    SSO_AVAILABLE = False
    print(f"⚠️ SSO module not available: {_sso_err}")

# ===== [v3.8.0] مطلوبیت‌های تدریس و زمان‌بندی اساتید =====
try:
    import preferences as prefs_module
    import slot_times as slot_times_module
    PREFERENCES_AVAILABLE = True
    try:
        prefs_module.ensure_preferences_tables(db)
    except Exception as _prefs_init_err:
        print(f"⚠️ preferences tables init error: {_prefs_init_err}")
except Exception as _prefs_err:
    PREFERENCES_AVAILABLE = False
    print(f"⚠️ preferences module not available: {_prefs_err}")

# ===== [v3.10.0] ماژول اساتید =====
try:
    import instructors as instructors_module
    INSTRUCTORS_AVAILABLE = True
    try:
        instructors_module.ensure_instructors_table(db)
    except Exception as _inst_init_err:
        print(f"⚠️ instructors table init error: {_inst_init_err}")
except Exception as _inst_err:
    INSTRUCTORS_AVAILABLE = False
    print(f"⚠️ instructors module not available: {_inst_err}")
# ===========================================

import sys
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["JSON_AS_ASCII"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SECRET_KEY"] = SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=ADMIN_SESSION_TTL)

db = Database()


# ==================================================
# Helpers — نظرسنجی فعال
# ==================================================

def get_active_survey_info():
    """در صورت نبود نظرسنجی فعال، مقادیر امن برمی‌گرداند."""
    s = db.get_active_survey()
    if not s:
        return {"id": None, "name": "بدون نظرسنجی فعال", "semester": "—",
                "year": "—", "deadline": "—", "start_date": None, "end_date": None}
    return {
        "id": s["id"], "name": s["name"],
        "semester": s.get("semester", "—"),
        "year": s.get("year", "—"),
        "deadline": s.get("deadline", "—"),
        "start_date": s.get("start_date"),
        "end_date": s.get("end_date"),
    }


@app.context_processor
def inject_globals():
    survey = get_active_survey_info()
    return {
        "APP_VERSION": APP_VERSION,
        "SEMESTER_LABEL": survey["name"],
        "SURVEY_DEADLINE": survey["deadline"],
        "APP_RELEASE_DATE": APP_RELEASE_DATE,
        "WEB_APP_URL": WEB_APP_URL,
        "SURVEY_ID": survey["id"],
        "MOBILE_APP_URL": MOBILE_APP_URL,
        "MOBILE_APP_NAME": MOBILE_APP_NAME,
        "MOBILE_APP_VERSION": MOBILE_APP_VERSION,
        "COMPANY_NAME": COMPANY_NAME,
        "COMPANY_URL": COMPANY_URL,
        # ===== [v3.7.0] SSO context =====
        "sso_enabled": sso_module.is_enabled() if SSO_AVAILABLE else False,
        "sso_button_label": (sso_module.load_settings().get("button_label") if SSO_AVAILABLE else ""),
        "website_url": WEBSITE_URL,
    }


def audit_log(action, target_type=None, target_id=None, description=None):
    admin = session.get("admin")
    if not admin:
        return
    try:
        db.add_audit_log(
            admin_id=admin["id"], admin_username=admin["username"],
            action=action, target_type=target_type, target_id=target_id,
            description=description, ip_address=request.remote_addr
        )
    except Exception as e:
        print(f"audit_log error: {e}")


# ==================================================
# Decorators
# ==================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = session.get("admin")
        if not admin:
            return redirect(url_for("admin_login", next=request.path))
        db_admin = db.get_admin_by_id(admin["id"])
        if not db_admin or not db_admin["is_active"]:
            session.pop("admin", None)
            flash("حساب کاربری شما غیرفعال شده است.", "error")
            return redirect(url_for("admin_login"))
        g.admin = dict(db_admin)
        session["admin"]["full_name"] = db_admin["full_name"]
        session["admin"]["role"] = db_admin["role"]
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        admin = session.get("admin")
        if not admin or admin.get("role") != "super_admin":
            flash("دسترسی فقط برای سوپر ادمین مجاز است.", "error")
            return redirect(url_for("admin_index"))
        return f(*args, **kwargs)
    return decorated


def admin_or_instructor_required(f):
    """دسترسی برای ادمین یا استاد (برای صفحات مطلوبیت‌ها).
    برای ادمین: از admin_users استفاده می‌کند
    برای استاد: از authorized_users استفاده می‌کند (بدون نیاز به /admin/login)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = session.get("admin")
        if not admin:
            return redirect(url_for("instructor_login", next=request.path))
        role = admin.get("role", "admin")
        # اگر استاد است
        if role == "instructor":
            # بررسی در authorized_users
            try:
                rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (admin.get("id"),))
                if not rows:
                    session.pop("admin", None)
                    flash("حساب کاربری شما غیرفعال شده است.", "error")
                    return redirect(url_for("instructor_login", next=request.path))
                user = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
                if user.get("is_blocked"):
                    session.pop("admin", None)
                    flash("حساب شما مسدود شده است.", "error")
                    return redirect(url_for("instructor_login", next=request.path))
                # تنظیم g.admin با اطلاعات استاد
                g.admin = {
                    "id": user["id"],
                    "username": user.get("student_number") or user.get("name") or "",
                    "full_name": user.get("name") or "",
                    "role": "instructor",
                }
            except Exception as e:
                print(f"admin_or_instructor_required instructor error: {e}")
                session.pop("admin", None)
                return redirect(url_for("instructor_login", next=request.path))
        else:
            # ادمین: بررسی در admin_users
            db_admin = db.get_admin_by_id(admin["id"])
            if not db_admin or not db_admin["is_active"]:
                session.pop("admin", None)
                flash("حساب کاربری شما غیرفعال شده است.", "error")
                return redirect(url_for("admin_login", next=request.path))
            g.admin = dict(db_admin)
            session["admin"]["full_name"] = db_admin["full_name"]
            session["admin"]["role"] = db_admin["role"]
        # بررسی نقش مجاز
        final_role = g.admin.get("role", "admin")
        if final_role not in ("super_admin", "admin", "instructor"):
            flash("دسترسی مجاز نیست.", "error")
            return redirect(url_for("login_choice"))
        return f(*args, **kwargs)
    return decorated


def instructor_only_required(f):
    """فقط استاد."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        admin = session.get("admin")
        if not admin:
            return redirect(url_for("admin_login"))
        if admin.get("role") != "instructor":
            flash("دسترسی فقط برای استاد مجاز است.", "error")
            return redirect(url_for("admin_index"))
        return f(*args, **kwargs)
    return decorated


def instructor_login_required(f):
    """دکوراتور مخصوص استاد — بررسی session['admin'] با role='instructor'.
    این دکوراتور از authorized_users استفاده می‌کند (نه admin_users)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = session.get("admin")
        if not admin:
            return redirect(url_for("instructor_login", next=request.path))
        # بررسی نقش instructor
        if admin.get("role") != "instructor":
            flash("دسترسی فقط برای استاد مجاز است.", "error")
            return redirect(url_for("login_choice"))
        # بررسی مسدود نبودن کاربر در authorized_users
        try:
            rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (admin.get("id"),))
            if not rows:
                # شاید در admin_users است (مثل ادمین‌های قدیمی)
                admin_row = db.get_admin_by_id(admin.get("id"))
                if not admin_row or not admin_row.get("is_active", 1):
                    session.pop("admin", None)
                    flash("حساب کاربری شما غیرفعال شده است.", "error")
                    return redirect(url_for("instructor_login"))
            else:
                user = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
                if user.get("is_blocked"):
                    session.pop("admin", None)
                    flash("حساب شما مسدود شده است.", "error")
                    return redirect(url_for("instructor_login"))
                # به‌روزرسانی g.admin با اطلاعات کاربر
                g.admin = {
                    "id": user["id"],
                    "username": user.get("student_number") or user.get("name") or "",
                    "full_name": user.get("name") or "",
                    "role": "instructor",
                }
        except Exception as e:
            print(f"instructor_login_required error: {e}")
            session.pop("admin", None)
            return redirect(url_for("instructor_login"))
        return f(*args, **kwargs)
    return decorated


def student_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        student = session.get("student")
        if not student:
            return redirect(url_for("student_login", next=request.path))
        g.student = student
        return f(*args, **kwargs)
    return decorated


# ==================================================
# Public Pages
# ==================================================

@app.route("/")
def index():
    stats = get_public_stats()
    survey = get_active_survey_info()
    return render_template("website/index.html", stats=stats, survey=survey)


@app.route("/dashboard")
def dashboard():
    stats = get_public_stats()
    survey = get_active_survey_info()
    return render_template("website/dashboard.html", stats=stats, survey=survey)


@app.route("/courses")
def courses():
    all_courses = db.get_all_courses(only_active=True)
    return render_template("website/courses.html", courses=all_courses)


@app.route("/about")
def about():
    return render_template("website/about.html")


@app.route("/login-choice")
def login_choice():
    """صفحه انتخاب نوع ورود — دانشجو، استاد یا ادمین"""
    survey = get_active_survey_info()
    # اگر دانشجو قبلاً وارد شده، به داشبورد هدایت شود
    if session.get("student"):
        return redirect(url_for("student_dashboard"))
    # اگر ادمین/استاد وارد شده، به پنل هدایت شود
    if session.get("admin"):
        return redirect(url_for("admin_index"))
    return render_template("website/login_selection.html", survey=survey)


@app.route("/instructor/login", methods=["GET", "POST"])
def instructor_login():
    """ورود استاد — جستجو در authorized_users (اساتید از طریق sync_to_users)."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("نام کاربری و رمز عبور را وارد کنید.", "error")
            return render_template("instructor/login.html")

        # جستجو در authorized_users (اساتید از طریق sync_to_users اینجا اضافه می‌شوند)
        # اول با student_number (که همان username است)
        user = db.get_user_by_student_number(username)
        # اگر پیدا نشد، با phone جستجو کن
        if not user:
            try:
                rows = db.execute_query(
                    "SELECT * FROM authorized_users WHERE display_phone = ? OR normalized_phone = ?",
                    (username, username)
                )
                if rows:
                    user = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
            except Exception:
                pass

        if not user:
            flash("نام کاربری یا رمز عبور نادرست است.", "error")
            return render_template("instructor/login.html")

        # بررسی مسدود بودن
        if user.get("is_blocked"):
            flash("حساب شما مسدود شده است.", "error")
            return render_template("instructor/login.html")

        # بررسی نقش: باید instructor باشد
        user_role = user.get("role") or ""
        user_type = user.get("user_type") or ""
        if user_role != "instructor" and user_type != "instructor":
            flash("این حساب برای ورود استاد نیست.", "error")
            return render_template("instructor/login.html")

        # بررسی رمز عبور
        if not db.verify_user_password(user, password):
            flash("نام کاربری یا رمز عبور نادرست است.", "error")
            return render_template("instructor/login.html")

        # ورود موفق
        db.record_login(user["id"], CHANNEL_WEBSITE,
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get("User-Agent", "")[:200])
        session.permanent = True
        session["admin"] = {
            "id": user["id"],
            "username": user.get("student_number") or user.get("name") or "",
            "full_name": user.get("name") or "",
            "role": "instructor",
        }
        flash("ورود موفقیت‌آمیز بود!", "success")
        # هدایت مستقیم به صفحه مطلوبیت‌ها
        return redirect(url_for("admin_preferences"))

    return render_template("instructor/login.html")


@app.route("/instructor/register", methods=["GET", "POST"])
def instructor_register():
    """ثبت‌نام استاد جدید (با تأیید ادمین)."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        instructor_code = (request.form.get("instructor_code") or "").strip()
        expert_group = (request.form.get("expert_group") or "").strip()
        cooperation_type = (request.form.get("cooperation_type") or "").strip()

        if not username or not password or not full_name:
            flash("نام کاربری، رمز عبور و نام کامل الزامی است.", "error")
            return render_template("instructor/register.html")

        if len(password) < 6:
            flash("رمز عبور باید حداقل ۶ کاراکتر باشد.", "error")
            return render_template("instructor/register.html")

        if password != confirm_password:
            flash("رمز عبور و تأییدیه آن یکسان نیستند.", "error")
            return render_template("instructor/register.html")

        # بررسی تکراری نبودن username
        existing = db.get_admin_by_username(username)
        if existing:
            flash("این نام کاربری قبلاً ثبت شده است.", "error")
            return render_template("instructor/register.html")

        # ساخت استاد جدید (به‌صورت غیرفعال تا ادمین تأیید کند)
        ok = db.create_admin(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
            role="instructor",
        )
        if not ok:
            flash("خطا در ثبت‌نام.", "error")
            return render_template("instructor/register.html")

        # ذخیره اطلاعات اضافی استاد در فایل mirror (بدون تغییر دیتابیس)
        import json
        instructor_extra_file = os.path.join(BASE_DIR, "instructor_profiles.json")
        try:
            data = {}
            if os.path.exists(instructor_extra_file):
                with open(instructor_extra_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[username] = {
                "instructor_code": instructor_code,
                "expert_group": expert_group,
                "cooperation_type": cooperation_type,
                "registered_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(instructor_extra_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"instructor profile save error: {e}")

        # فعال‌سازی خودکار اگر اولین استاد بود (یا باید ادمین تأیید کند)
        flash("ثبت‌نام شما با موفقیت انجام شد. ادمین سامانه باید حساب شما را فعال کند.", "success")
        return redirect(url_for("instructor_login"))

    return render_template("instructor/register.html")


@app.route("/instructor/dashboard")
@instructor_login_required
def instructor_dashboard():
    """داشبورد استاد — دسترسی به مطلوبیت‌ها + داشبورد فقط‌خواندنی."""
    admin = g.admin
    if not admin or admin.get("role") != "instructor":
        flash("دسترسی فقط برای استاد مجاز است.", "error")
        return redirect(url_for("admin_index"))

    # آمار کلی برای داشبورد فقط‌خواندنی
    total_users = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"]
    total_requests = db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"]
    total_courses = db.execute_query("SELECT COUNT(*) AS c FROM courses WHERE is_active=1")[0]["c"]

    # آمار مطلوبیت‌های این استاد
    instructor_username = admin.get("username", "")
    my_teaching_prefs = []
    my_time_prefs = []
    if PREFERENCES_AVAILABLE:
        all_teaching = prefs_module.get_all_teaching_preferences(db)
        my_teaching_prefs = [p for p in all_teaching if p.get("instructor_username") == instructor_username
                            or p.get("instructor_code") == instructor_username]
        all_time = prefs_module.get_all_time_preferences(db)
        my_time_prefs = [p for p in all_time if p.get("instructor_username") == instructor_username
                        or p.get("instructor_code") == instructor_username]

    survey = get_active_survey_info()

    return render_template(
        "instructor/dashboard.html",
        admin=admin,
        total_users=total_users,
        total_requests=total_requests,
        total_courses=total_courses,
        my_teaching_count=len(my_teaching_prefs),
        my_time_count=len(my_time_prefs),
        survey=survey,
    )


@app.route("/download-app")
def download_app():
    """صفحه دانلود اپلیکیشن موبایل دانشجو360"""
    survey = get_active_survey_info()
    # بررسی وجود فایل‌های APK
    import os
    apk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "downloads")
    apks = []
    if os.path.exists(apk_dir):
        for f in sorted(os.listdir(apk_dir)):
            if f.endswith(".apk"):
                size_kb = os.path.getsize(os.path.join(apk_dir, f)) // 1024
                apks.append({"filename": f, "size_kb": size_kb})
    return render_template(
        "website/download_app.html",
        survey=survey,
        apks=apks,
    )


@app.route("/download/apk/<filename>")
def download_apk(filename):
    """دانلود مستقیم فایل APK"""
    from flask import send_from_directory, abort
    import os
    apk_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "downloads")
    # جلوگیری از path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(404)
    full_path = os.path.join(apk_dir, filename)
    if not os.path.exists(full_path):
        abort(404)
    return send_from_directory(
        apk_dir, filename,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.android.package-archive"
    )


# ==================================================
# Student Registration & Login (جدید v2.2.0)
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        student_number = (request.form.get("student_number") or "").strip()
        student_type = request.form.get("student_type", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # اعتبارسنجی
        if not name or not phone or not student_number or not password:
            flash("همه فیلدها الزامی هستند.", "error")
            return render_template("website/register.html")

        # ===== [v3.6.1] اعتبارسنجی دقیق شماره تلفن: دقیقاً ۱۱ رقم با پیشوند 09 =====
        # فقط ارقام فارسی/عربی/انگلیسی را بپذیر و نرمال‌سازی کن
        phone_digits = "".join(c for c in phone if c.isdigit() or c in "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")
        phone_norm = helpers.normalize_digits(phone_digits)
        if len(phone_norm) != 11 or not phone_norm.startswith("09"):
            flash("شماره تماس باید دقیقاً ۱۱ رقم و با پیشوند 09 باشد. مثال: 09123456789", "error")
            return render_template("website/register.html")

        # اعتبارسنجی شماره دانشجویی (همان منطق بات)
        sn_digits = "".join(c for c in student_number if c.isdigit() or c in "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")
        sn_norm = helpers.normalize_digits(sn_digits)
        if len(sn_norm) not in (9, 14):
            flash("شماره دانشجویی باید ۹ یا ۱۴ رقم باشد.", "error")
            return render_template("website/register.html")

        valid, role_or_error = db.validate_student_number(sn_norm)
        if not valid:
            flash(role_or_error, "error")
            return render_template("website/register.html")

        if student_type not in ("پیوسته", "ناپیوسته"):
            flash("نوع کارشناسی را انتخاب کنید.", "error")
            return render_template("website/register.html")

        if len(password) < 6:
            flash("رمز عبور باید حداقل ۶ کاراکتر باشد.", "error")
            return render_template("website/register.html")

        # ===== [v3.6.1] تأیید رمز عبور =====
        if not confirm_password:
            flash("تأیید رمز عبور الزامی است.", "error")
            return render_template("website/register.html")
        if password != confirm_password:
            flash("رمز عبور و تأییدیه آن یکسان نیستند. لطفاً دوباره وارد کنید.", "error")
            return render_template("website/register.html")

        # جلوگیری از ثبت تکراری
        if db.user_exists(phone_norm, sn_norm):
            flash("این شماره تماس یا شماره دانشجویی قبلاً ثبت شده است.", "error")
            return render_template("website/register.html")

        # تعیین نقش
        role = "admin" if helpers.is_admin_student_number(sn_norm) else "user"
        if role == "admin":
            student_type = "پیوسته"
            if db.count_admins() >= 2:
                flash("حداکثر دو ادمین مجاز است.", "error")
                return render_template("website/register.html")

        ok = db.add_authorized_user(
            name, phone_norm, sn_norm, student_type, role,
            first_channel=CHANNEL_WEBSITE,
            password_hash=hash_password(password)
        )
        if not ok:
            flash("خطا در ثبت‌نام.", "error")
            return render_template("website/register.html")

        # ورود خودکار
        user = db.is_user_authorized(phone_norm)
        if user:
            db.record_login(user["id"], CHANNEL_WEBSITE,
                            ip_address=request.remote_addr,
                            user_agent=request.headers.get("User-Agent", "")[:200])
            session.permanent = True
            session["student"] = {
                "id": user["id"], "name": user["name"],
                "student_number": user["student_number"],
                "student_type": user["student_type"],
                "is_admin": user["role"] == "admin",
            }

        flash("ثبت‌نام موفقیت‌آمیز بود! وارد شدید.", "success")
        return redirect(url_for("student_dashboard"))

    return render_template("website/register.html")


@app.route("/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        student_number = (request.form.get("student_number") or "").strip()
        password = request.form.get("password", "")

        sn_norm = helpers.normalize_digits(student_number)
        user = db.get_user_by_student_number(sn_norm)

        if not user:
            flash("شماره دانشجویی یا رمز عبور نادرست است.", "error")
            return render_template("website/login.html")

        if user.get("is_blocked"):
            flash("حساب شما مسدود شده است.", "error")
            return render_template("website/login.html")

        if not db.verify_user_password(user, password):
            flash("شماره دانشجویی یا رمز عبور نادرست است.", "error")
            return render_template("website/login.html")

        db.record_login(user["id"], CHANNEL_WEBSITE,
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get("User-Agent", "")[:200])

        session.permanent = True
        session["student"] = {
            "id": user["id"], "name": user["name"],
            "student_number": user["student_number"],
            "student_type": user["student_type"],
            "is_admin": user["role"] == "admin",
        }
        flash("خوش آمدید!", "success")
        next_url = request.args.get("next") or url_for("student_dashboard")
        return redirect(next_url)

    return render_template("website/login.html")


@app.route("/logout")
def student_logout():
    session.pop("student", None)
    flash("با موفقیت خارج شدید.", "success")
    return redirect(url_for("index"))


@app.route("/student")
@student_login_required
def student_dashboard():
    """داشبورد دانشجو در وب‌سایت"""
    user_id = g.student["id"]
    user = db.is_user_authorized(g.student["student_number"]) if False else None
    # بهتر است با id بگیریم
    rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (user_id,))
    user = dict(rows[0]) if rows else None

    if not user:
        session.pop("student", None)
        return redirect(url_for("student_login"))

    if user.get("is_blocked"):
        session.pop("student", None)
        flash("حساب شما مسدود شده است.", "error")
        return redirect(url_for("student_login"))

    survey = get_active_survey_info()
    user_requests = db.get_user_requests(user_id)
    has_submitted = db.has_user_submitted_courses(user_id, survey["id"]) if survey["id"] else False
    available_courses = []
    if not has_submitted:
        if user["role"] == "admin" and not user.get("student_type"):
            available_courses = db.get_all_courses()
        else:
            available_courses = helpers.get_available_courses_for_user(db, user)

    return render_template(
        "website/student_dashboard.html",
        user=user, survey=survey,
        my_requests=user_requests,
        has_submitted=has_submitted,
        available_courses=available_courses,
        max_courses=MAX_COURSES_PER_USER,
        is_admin=user["role"] == "admin",
    )


@app.route("/student/submit", methods=["POST"])
@student_login_required
def student_submit_courses():
    user_id = g.student["id"]
    user_rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (user_id,))
    if not user_rows:
        return redirect(url_for("student_login"))
    user = dict(user_rows[0])

    survey = get_active_survey_info()
    if not survey["id"]:
        flash("هیچ نظرسنجی فعالی وجود ندارد.", "error")
        return redirect(url_for("student_dashboard"))

    if user["role"] != "admin" and db.has_user_submitted_courses(user_id, survey["id"]):
        flash("شما قبلاً پیشنهاد ثبت کرده‌اید.", "error")
        return redirect(url_for("student_dashboard"))

    course_ids = request.form.getlist("course_ids")
    course_ids = [int(c) for c in course_ids if c.isdigit()]

    if not course_ids:
        flash("حداقل یک درس انتخاب کنید.", "error")
        return redirect(url_for("student_dashboard"))

    # ===== [v3.6.1] محدودیت ۵ درس، با استثنای کارآموزی و پروژه =====
    # درس‌هایی که در عنوانشان "کارآموزی" یا "پروژه" دارند از محدودیت ۵ تایی مستثنی هستند
    EXEMPT_KEYWORDS = ("کارآموزی", "پروژه")
    exempt_ids = set()
    if course_ids:
        placeholders = ",".join("?" * len(course_ids))
        rows = db.execute_query(
            f"SELECT id, course_title FROM courses WHERE id IN ({placeholders})",
            tuple(course_ids)
        )
        for r in rows:
            title = (r.get("course_title") if isinstance(r, dict) else r[1]) or ""
            if any(kw in title for kw in EXEMPT_KEYWORDS):
                exempt_ids.add(r.get("id") if isinstance(r, dict) else r[0])
    non_exempt_count = len([c for c in course_ids if c not in exempt_ids])
    if non_exempt_count > MAX_COURSES_PER_USER:
        flash(f"حداکثر {MAX_COURSES_PER_USER} درس می‌توانید انتخاب کنید (به جز کارآموزی و پروژه).", "error")
        return redirect(url_for("student_dashboard"))

    if user["role"] == "admin" and not user.get("student_type"):
        allowed = db.get_all_courses()
    else:
        allowed = helpers.get_available_courses_for_user(db, user)
    allowed_ids = {c["id"] for c in allowed}

    success = 0
    for cid in course_ids:
        if cid in allowed_ids:
            if db.add_user_course(user_id, cid, survey_id=survey["id"], channel=CHANNEL_WEBSITE):
                success += 1

    if success > 0:
        flash(f"{success} درس با موفقیت ثبت شد.", "success")
    else:
        flash("ثبت ناموفق بود.", "error")
    return redirect(url_for("student_dashboard"))


# ==================================================
# Public API
# ==================================================

@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


def get_public_stats():
    total_users = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"]
    total_requests = db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"]
    participants = db.execute_query(
        "SELECT COUNT(DISTINCT user_id) AS c FROM course_requests"
    )[0]["c"]
    total_courses = db.execute_query(
        "SELECT COUNT(*) AS c FROM courses WHERE is_active=1"
    )[0]["c"]
    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "participants": participants,
        "total_courses": total_courses,
        "top_courses": db.get_top_courses(10),
        "sections": db.get_section_distribution(),
        "daily": db.get_daily_requests(30),
    }


@app.route("/api/public/stats")
def api_public_stats():
    survey = get_active_survey_info()
    return jsonify({
        "ok": True,
        "semester": survey["name"],
        "survey_id": survey["id"],
        "deadline": survey["deadline"],
        "version": APP_VERSION,
        "stats": get_public_stats(),
    })


@app.route("/api/public/courses")
def api_public_courses():
    courses = db.get_all_courses(only_active=True)
    return jsonify({
        "ok": True,
        "courses": [
            {
                "id": c["id"], "title": c["course_title"],
                "section": c.get("section") or "",
                "section_label": helpers.SECTION_LABELS.get(c.get("section"), c.get("section") or ""),
                "credits": c.get("credits") or "",
                "prerequisite": c.get("prerequisite") or "",
                "year": c.get("year"),
            }
            for c in courses
        ]
    })


# ==================================================
# Admin Authentication
# ==================================================

# ==================================================
# ===== [v3.7.0] مسیرهای ورود یکپارچه (SSO) =====
# ==================================================

@app.route("/api/auth/sso/login")
def sso_login():
    """شروع جریان ورود SSO — ریدایرکت به authorization endpoint."""
    if not SSO_AVAILABLE:
        flash("ماژول SSO در دسترس نیست.", "error")
        return redirect(url_for("student_login"))
    if not sso_module.is_enabled():
        return redirect(url_for("student_login") + "?sso_error=disabled")
    settings = sso_module.load_settings()

    # تعیین مقصد بازگشت
    client = request.args.get("client", "web")
    if client == "mobile":
        redirect_after = settings.get("mobile_redirect") or "/app/dashboard"
    else:
        redirect_after = settings.get("web_redirect") or "/student"

    # تولید state, nonce, code_verifier
    state, nonce = sso_module.generate_state_nonce()
    code_verifier, code_challenge = sso_module.generate_pkce()

    # redirect_uri ثابت (مطابق با clients.json)
    redirect_uri = f"{WEBSITE_URL}/api/auth/sso/callback"

    # ذخیره در کوکی HttpOnly
    import datetime as _dt
    resp = redirect(sso_module.build_authorization_url(state, nonce, code_challenge, redirect_uri)[0]
                    or url_for("student_login") + "?sso_error=config_incomplete")
    expiry = _dt.datetime.now() + _dt.timedelta(minutes=10)
    resp.set_cookie("sso_state", state, httponly=True, samesite="Lax", expires=expiry, secure=False)
    resp.set_cookie("sso_nonce", nonce, httponly=True, samesite="Lax", expires=expiry, secure=False)
    resp.set_cookie("sso_verifier", code_verifier, httponly=True, samesite="Lax", expires=expiry, secure=False)
    resp.set_cookie("sso_redirect", redirect_after, httponly=True, samesite="Lax", expires=expiry, secure=False)
    return resp


@app.route("/api/auth/sso/callback")
def sso_callback():
    """بازگشتی از سرور SSO — دریافت کد و تبادل برای توکن."""
    if not SSO_AVAILABLE:
        return redirect(url_for("student_login") + "?sso_error=disabled")

    # پارامترهای ورودی
    error = request.args.get("error")
    code = request.args.get("code")
    state = request.args.get("state")

    if error:
        return _sso_fail(error)

    if not code:
        return _sso_fail("invalid_request")

    # اعتبارسنجی state
    cookie_state = request.cookies.get("sso_state")
    if not cookie_state or cookie_state != state:
        return _sso_fail("state")

    cookie_nonce = request.cookies.get("sso_nonce")
    code_verifier = request.cookies.get("sso_verifier")
    redirect_after = request.cookies.get("sso_redirect") or "/student"

    settings = sso_module.load_settings()
    redirect_uri = f"{WEBSITE_URL}/api/auth/sso/callback"

    endpoints, ep_err = sso_module.get_endpoints()
    if ep_err:
        return _sso_fail("idp_unreachable")

    # تبادل کد برای توکن
    token_resp, t_err = sso_module.exchange_code(
        code=code,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        client_id=settings["client_id"],
        token_endpoint=endpoints["token_endpoint"],
    )
    if t_err:
        # نگاشت خطاها
        if "invalid_grant" in t_err:
            return _sso_fail("expired")
        if "429" in t_err or "rate" in t_err.lower():
            return _sso_fail("rate")
        return _sso_fail("idp_unreachable")

    id_token = token_resp.get("id_token")
    access_token = token_resp.get("access_token") or ""

    # اعتبارسنجی id_token
    claims, v_err = sso_module.validate_id_token(
        id_token=id_token,
        expected_issuer=settings["issuer"],
        expected_aud=settings["client_id"],
        expected_nonce=cookie_nonce or "",
    )
    if v_err and "signature_not_validated" not in v_err:
        if "expired" in v_err:
            return _sso_fail("expired")
        if "iss" in v_err:
            return _sso_fail("iss")
        if "aud" in v_err:
            return _sso_fail("aud")
        if "nonce" in v_err:
            return _sso_fail("nonce")
        return _sso_fail("invalid_token:" + v_err)

    # گرفتن اطلاعات کاربر از userinfo (اختیاری)
    userinfo = {}
    if endpoints.get("userinfo_endpoint") and access_token:
        ui, ui_err = sso_module.fetch_userinfo(
            endpoints["userinfo_endpoint"], access_token
        )
        if not ui_err:
            userinfo = ui

    # ادغام claims با userinfo
    sub = claims.get("sub") or userinfo.get("sub")
    preferred_username = (claims.get("preferred_username")
                          or userinfo.get("preferred_username")
                          or "")
    name = (claims.get("name") or userinfo.get("name") or preferred_username or "")
    email = (claims.get("email") or userinfo.get("email") or "")

    # استخراج نقش‌ها
    roles = sso_module.extract_roles(claims, settings["client_id"])
    final_role = sso_module.determine_role(roles, settings.get("default_role", "user"))

    # پاک‌سازی کوکی‌های SSO
    resp = redirect(redirect_after)
    resp.delete_cookie("sso_state")
    resp.delete_cookie("sso_nonce")
    resp.delete_cookie("sso_verifier")
    resp.delete_cookie("sso_redirect")

    # ==================================================
    # اتصال / ساخت حساب کاربری محلی
    # ==================================================
    user_id = sso_module.find_local_user_by_sub(sub)
    if user_id is None:
        # پیدا کردن با username
        if preferred_username:
            try:
                existing = db.execute_query(
                    "SELECT id FROM authorized_users WHERE student_number = ? OR phone = ?",
                    (preferred_username, preferred_username)
                )
                if existing:
                    user_id = existing[0]["id"] if isinstance(existing[0], dict) else existing[0][0]
                    # اتصال sub
                    sso_module.link_user(sub, user_id, preferred_username, name)
            except Exception as e:
                print(f"SSO find user error: {e}")

    if user_id is None and settings.get("auto_create_account"):
        # ساخت حساب جدید
        try:
            # تولید رمز تصادفی (کاربر از طریق SSO وارد می‌شود، رمز لازم نیست)
            import secrets as _secrets
            random_pw = _secrets.token_urlsafe(32)
            # اگر ادمین بود و تعداد ادمین‌ها کافی بود، نقش user بده
            actual_role = final_role
            if actual_role == "admin":
                try:
                    admin_count = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users WHERE role = 'admin'")
                    if admin_count and admin_count[0]["c"] >= 2:
                        actual_role = "user"
                except Exception:
                    actual_role = "user"
            # تعیین student_type پیش‌فرض
            student_type = "ناپیوسته"
            ok = db.add_authorized_user(
                name=name or preferred_username,
                phone=preferred_username or sub[:11],
                student_number=preferred_username or sub[:9],
                student_type=student_type,
                role=actual_role,
                first_channel="sso",
                password_hash=hash_password(random_pw),
            )
            if ok:
                # گرفتن user_id
                rows = db.execute_query(
                    "SELECT id FROM authorized_users WHERE phone = ? OR student_number = ?",
                    (preferred_username or sub[:11], preferred_username or sub[:9])
                )
                if rows:
                    user_id = rows[0]["id"] if isinstance(rows[0], dict) else rows[0][0]
                    sso_module.link_user(sub, user_id, preferred_username, name)
        except Exception as e:
            print(f"SSO create user error: {e}")

    if user_id is None:
        return _sso_fail("no_user")

    # ورود کاربر به نشست محلی
    try:
        rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (user_id,))
        if not rows:
            return _sso_fail("no_user")
        user = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
        db.record_login(user["id"], "sso",
                        ip_address=request.remote_addr,
                        user_agent=request.headers.get("User-Agent", "")[:200])
        session.permanent = True
        # اگر استاد است، در session["admin"] ذخیره کن تا به داشبورد استاد برود
        user_role = user.get("role") or ""
        user_type = user.get("user_type") or ""
        if user_role == "instructor" or user_type == "instructor":
            session["admin"] = {
                "id": user["id"],
                "username": user.get("student_number") or user.get("name") or "",
                "full_name": user.get("name") or "",
                "role": "instructor",
            }
            flash("ورود موفقیت‌آمیز بود! (از طریق SSO — استاد)", "success")
            # هدایت مستقیم به صفحه مطلوبیت‌ها
            return redirect(url_for("admin_preferences"))
        elif user_role == "admin":
            session["admin"] = {
                "id": user["id"],
                "username": user.get("student_number") or user.get("name") or "",
                "full_name": user.get("name") or "",
                "role": "admin",
            }
            flash("ورود موفقیت‌آمیز بود! (از طریق SSO — ادمین)", "success")
            return redirect(url_for("admin_index"))
        else:
            session["student"] = {
                "id": user["id"], "name": user["name"],
                "student_number": user["student_number"],
                "student_type": user["student_type"],
                "is_admin": False,
            }
            flash("ورود موفقیت‌آمیز بود! (از طریق SSO)", "success")
    except Exception as e:
        print(f"SSO session error: {e}")
        return _sso_fail("session_error:" + str(e))

    flash("ورود موفقیت‌آمیز بود! (از طریق SSO)", "success")
    return resp


@app.route("/api/auth/sso/logout")
def sso_logout():
    """خروج از SSO — ابطال نشست محلی و ریدایرکت به end_session."""
    if not SSO_AVAILABLE:
        return redirect(url_for("index"))
    session.pop("student", None)
    settings = sso_module.load_settings()
    post_logout = f"{WEBSITE_URL}/?loggedOut=1"
    logout_url = sso_module.build_logout_url(post_logout_uri=post_logout)
    if logout_url:
        return redirect(logout_url)
    return redirect(url_for("index") + "?loggedOut=1")


def _sso_fail(error_code):
    """هد打扮 خطای SSO به صفحه ورود با پیام فارسی."""
    msg = sso_module.get_error_message(error_code)
    flash(f"خطای ورود یکپارچه: {msg}", "error")
    return redirect(url_for("student_login") + f"?sso_error={error_code}")


# ==================================================
# ===== [v3.7.0] مسیرهای ادمین برای پیکربندی SSO =====
# ==================================================

@app.route("/admin/sso")
@login_required
def admin_sso():
    """صفحه پیکربندی SSO."""
    settings = sso_module.load_settings() if SSO_AVAILABLE else {}
    return render_template("admin/sso.html", settings=settings, admin=g.admin,
                           website_url=WEBSITE_URL)


@app.route("/admin/sso/save", methods=["POST"])
@login_required
def admin_sso_save():
    """ذخیره تنظیمات SSO."""
    if not SSO_AVAILABLE:
        flash("ماژول SSO در دسترس نیست.", "error")
        return redirect(url_for("admin_sso"))
    new_settings = {
        "enabled": bool(request.form.get("enabled")),
        "issuer": (request.form.get("issuer") or "").strip().rstrip("/"),
        "client_id": (request.form.get("client_id") or "").strip(),
        "scope": (request.form.get("scope") or "openid profile email").strip(),
        "default_role": request.form.get("default_role") or "user",
        "auto_create_account": bool(request.form.get("auto_create_account")),
        "button_label": (request.form.get("button_label") or "ورود با حساب سازمانی").strip(),
        "web_redirect": (request.form.get("web_redirect") or "/student").strip(),
        "mobile_redirect": (request.form.get("mobile_redirect") or "/app/dashboard").strip(),
    }
    ok = sso_module.save_settings(new_settings)
    audit_log("sso_settings_update", description="به‌روزرسانی تنظیمات SSO")
    if ok:
        flash("تنظیمات SSO ذخیره شد.", "success")
    else:
        flash("خطا در ذخیره تنظیمات.", "error")
    return redirect(url_for("admin_sso"))


@app.route("/admin/sso/test", methods=["POST"])
@login_required
def admin_sso_test():
    """تست اتصال به سرور SSO."""
    if not SSO_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable",
                        "message": "ماژول SSO در دسترس نیست."})
    result = sso_module.test_connection()
    return jsonify(result)


# ==================================================
# ===== [v3.8.0] مسیرهای API مطلوبیت‌ها =====
# ==================================================

# --- Slot Times (منبع مرجع) ---
@app.route("/api/slot-times/search")
def api_slot_times_search():
    """گرفتن اسلات‌های معتبر برای ترم و واحد مشخص."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    term = request.args.get("term", "mehr")
    units = int(request.args.get("units", 2))
    period = request.args.get("period", "")
    data = slot_times_module.get_slots(term=term, units=units, period=period)
    return jsonify({"ok": True, "term": slot_times_module.normalize_term(term), **data})


@app.route("/api/slot-times/terms")
def api_slot_times_terms():
    """لیست ترم‌های معتبر."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    return jsonify({"ok": True, **slot_times_module.get_terms()})


@app.route("/api/slot-times/schedule")
def api_slot_times_schedule():
    """برنامه کامل اسلات‌های یک ترم."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    term = request.args.get("term", "mehr")
    return jsonify({"ok": True, **slot_times_module.get_schedule(term=term)})


# --- Teaching Preferences ---
@app.route("/api/teaching-preferences")
@admin_or_instructor_required
def api_teaching_preferences_list():
    """لیست مطلوبیت‌های تدریس."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    term_code = request.args.get("term_code")
    instructor_code = request.args.get("instructor_code")
    items = prefs_module.get_all_teaching_preferences(db, term_code=term_code, instructor_code=instructor_code)
    return jsonify({"ok": True, "items": items, "count": len(items)})


@app.route("/api/teaching-preferences", methods=["POST"])
@admin_or_instructor_required
def api_teaching_preferences_create():
    """ساخت مطلوبیت تدریس جدید."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    if not data.get("course_name") or not data.get("instructor_name"):
        return jsonify({"ok": False, "error": "نام درس و نام استاد الزامی است"}), 400
    pref_id, err = prefs_module.create_teaching_preference(db, data)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    audit_log("teaching_pref_create", description=f"ساخت مطلوبیت تدریس #{pref_id}")
    return jsonify({"ok": True, "id": pref_id})


@app.route("/api/teaching-preferences/<int:pref_id>", methods=["PUT"])
@login_required
def api_teaching_preferences_update(pref_id):
    """ویرایش مطلوبیت تدریس."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    ok, err = prefs_module.update_teaching_preference(db, pref_id, data)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "رکورد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("teaching_pref_update", description=f"ویرایش مطلوبیت تدریس #{pref_id}")
    return jsonify({"ok": True})


@app.route("/api/teaching-preferences/<int:pref_id>", methods=["DELETE"])
@login_required
def api_teaching_preferences_delete(pref_id):
    """حذف مطلوبیت تدریس."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    ok, err = prefs_module.delete_teaching_preference(db, pref_id)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "رکورد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("teaching_pref_delete", description=f"حذف مطلوبیت تدریس #{pref_id}")
    return jsonify({"ok": True, "message": "رکورد با موفقیت حذف شد"})


@app.route("/api/teaching-preferences/upload", methods=["POST"])
@login_required
def api_teaching_preferences_upload():
    """آپلود اکسل مطلوبیت‌های تدریس."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "فایل ارسال نشده"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "فرمت فایل باید اکسل باشد"}), 400
    # ذخیره موقت
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        f.save(tmp.name)
        result = prefs_module.import_teaching_preferences_excel(db, tmp.name)
        os.unlink(tmp.name)
    audit_log("teaching_pref_upload", description=f"آپلود اکسل مطلوبیت تدریس: {result.get('count', 0)} رکورد")
    status_code = result.pop("status_code", 200) if "status_code" in result else 200
    return jsonify({"ok": status_code == 200, **result}), status_code


# --- Time Preferences ---
@app.route("/api/time-preferences")
@admin_or_instructor_required
def api_time_preferences_list():
    """لیست مطلوبیت‌های زمان‌بندی."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    instructor_code = request.args.get("instructor_code")
    day = request.args.get("day")
    items = prefs_module.get_all_time_preferences(db, instructor_code=instructor_code, day=day)
    return jsonify({"ok": True, "items": items, "count": len(items)})


@app.route("/api/time-preferences", methods=["POST"])
@admin_or_instructor_required
def api_time_preferences_create():
    """ساخت مطلوبیت زمان‌بندی جدید."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    if not data.get("day") or not data.get("instructor_name"):
        return jsonify({"ok": False, "error": "روز و نام استاد الزامی است"}), 400
    pref_id, err = prefs_module.create_time_preference(db, data)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    audit_log("time_pref_create", description=f"ساخت مطلوبیت زمان #{pref_id}")
    return jsonify({"ok": True, "id": pref_id})


@app.route("/api/time-preferences/bulk", methods=["POST"])
@admin_or_instructor_required
def api_time_preferences_bulk_create():
    """ساخت چندین مطلوبیت زمان‌بندی به‌صورت یکجا (برای TimeSlotSelector)."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"ok": False, "error": "لطفاً حداقل یک بازه زمانی انتخاب کنید."}), 400
    created_ids = []
    for item in items:
        pref_id, err = prefs_module.create_time_preference(db, item)
        if err is None:
            created_ids.append(pref_id)
    audit_log("time_pref_bulk_create", description=f"ساخت {len(created_ids)} مطلوبیت زمان")
    return jsonify({"ok": True, "count": len(created_ids), "ids": created_ids})


@app.route("/api/time-preferences/<int:pref_id>", methods=["PUT"])
@login_required
def api_time_preferences_update(pref_id):
    """ویرایش مطلوبیت زمان‌بندی."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    ok, err = prefs_module.update_time_preference(db, pref_id, data)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "رکورد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("time_pref_update", description=f"ویرایش مطلوبیت زمان #{pref_id}")
    return jsonify({"ok": True})


@app.route("/api/time-preferences/<int:pref_id>", methods=["DELETE"])
@login_required
def api_time_preferences_delete(pref_id):
    """حذف مطلوبیت زمان‌بندی."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    ok, err = prefs_module.delete_time_preference(db, pref_id)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "رکورد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("time_pref_delete", description=f"حذف مطلوبیت زمان #{pref_id}")
    return jsonify({"ok": True, "message": "رکورد با موفقیت حذف شد"})


@app.route("/api/time-preferences/upload", methods=["POST"])
@login_required
def api_time_preferences_upload():
    """آپلود اکسل مطلوبیت‌های زمان‌بندی با پارامتر term."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "فایل ارسال نشده"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "فرمت فایل باید اکسل باشد"}), 400
    term = request.args.get("term", "mehr") or request.form.get("term", "mehr")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        f.save(tmp.name)
        result = prefs_module.import_time_preferences_excel(db, tmp.name, term=term)
        os.unlink(tmp.name)
    audit_log("time_pref_upload", description=f"آپلود اکسل مطلوبیت زمان: {result.get('count', 0)} رکورد")
    status_code = result.pop("status_code", 200) if "status_code" in result else 200
    return jsonify({"ok": status_code == 200, **result}), status_code


# --- صفحه‌های ادمین برای مطلوبیت‌ها ---
@app.route("/admin/preferences")
@admin_or_instructor_required
def admin_preferences():
    """صفحه مدیریت مطلوبیت‌های اساتید — ادمین همه را می‌بیند، استاد فقط خودش را."""
    if not PREFERENCES_AVAILABLE:
        return render_template("admin/preferences_unavailable.html", admin=g.admin)
    # اگر استاد است، فقط مطلوبیت‌های خودش را ببیند
    if g.admin.get("role") == "instructor":
        instructor_username = g.admin.get("username", "")
        all_teaching = prefs_module.get_all_teaching_preferences(db)
        teaching_items = [p for p in all_teaching if p.get("instructor_username") == instructor_username
                         or p.get("instructor_code") == instructor_username]
        all_time = prefs_module.get_all_time_preferences(db)
        time_items = [p for p in all_time if p.get("instructor_username") == instructor_username
                     or p.get("instructor_code") == instructor_username]
        unique_courses = db.execute_query("SELECT unique_code, title FROM unique_courses ORDER BY title") or []
        terms = slot_times_module.get_terms()["terms"]
        # گرفتن max_teaching_units استاد
        max_units = 0
        if INSTRUCTORS_AVAILABLE:
            inst_rows = db.execute_query("SELECT max_teaching_units FROM instructors WHERE username = ? OR code = ?", (instructor_username, instructor_username))
            if inst_rows:
                max_units = (inst_rows[0]["max_teaching_units"] if isinstance(inst_rows[0], dict) else inst_rows[0][0]) or 0
        return render_template(
            "admin/preferences.html",
            teaching_items=teaching_items,
            time_items=time_items,
            unique_courses=[dict(r) if not isinstance(r, dict) else r for r in unique_courses],
            terms=terms,
            admin=g.admin,
            is_instructor=True,
            max_teaching_units=max_units,
        )
    teaching_items = prefs_module.get_all_teaching_preferences(db)
    time_items = prefs_module.get_all_time_preferences(db)
    unique_courses = db.execute_query("SELECT unique_code, title FROM unique_courses ORDER BY title") or []
    terms = slot_times_module.get_terms()["terms"]
    return render_template(
        "admin/preferences.html",
        teaching_items=teaching_items,
        time_items=time_items,
        unique_courses=[dict(r) if not isinstance(r, dict) else r for r in unique_courses],
        terms=terms,
        admin=g.admin,
    )


# ==================================================
# ===== [v3.10.0] مسیرهای اساتید =====
# ==================================================

@app.route("/api/courses/unique")
@admin_or_instructor_required
def api_courses_unique_list():
    """لیست دروس یکتا — برای استفاده در Course Picker."""
    rows = db.execute_query(
        """SELECT uc.unique_code AS id, uc.unique_code, uc.title, uc.course_group,
           (SELECT credits FROM courses WHERE unique_code = uc.unique_code AND credits IS NOT NULL LIMIT 1) AS credits
           FROM unique_courses uc WHERE uc.is_active = 1 ORDER BY uc.title"""
    )
    items = [dict(r) if not isinstance(r, dict) else r for r in rows] if rows else []
    return jsonify({"ok": True, "items": items, "count": len(items)})


@app.route("/api/instructors")
@login_required
def api_instructors_list():
    """لیست اساتید."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    search = request.args.get("search", "")
    cooperation_type = request.args.get("cooperation_type", "")
    items = instructors_module.get_all_instructors(db, search=search, cooperation_type=cooperation_type)
    return jsonify({"ok": True, "items": items, "count": len(items)})


@app.route("/api/instructors", methods=["POST"])
@login_required
def api_instructors_create():
    """ساخت استاد جدید."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    if not data.get("full_name") and not (data.get("first_name") or data.get("last_name")):
        return jsonify({"ok": False, "error": "نام الزامی است"}), 400
    inst_id, err = instructors_module.create_instructor(db, data)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    audit_log("instructor_create", description=f"ساخت استاد #{inst_id}")
    return jsonify({"ok": True, "id": inst_id})


@app.route("/api/instructors/<int:inst_id>", methods=["PUT"])
@login_required
def api_instructors_update(inst_id):
    """ویرایش استاد."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    ok, err = instructors_module.update_instructor(db, inst_id, data)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "استاد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("instructor_update", description=f"ویرایش استاد #{inst_id}")
    return jsonify({"ok": True})


@app.route("/api/instructors/<int:inst_id>", methods=["DELETE"])
@login_required
def api_instructors_delete(inst_id):
    """حذف استاد."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    ok, err = instructors_module.delete_instructor(db, inst_id)
    if err:
        if "پیدا نشد" in err:
            return jsonify({"ok": False, "error": "استاد پیدا نشد"}), 404
        return jsonify({"ok": False, "error": err}), 500
    audit_log("instructor_delete", description=f"حذف استاد #{inst_id}")
    return jsonify({"ok": True, "message": "استاد با موفقیت حذف شد"})


@app.route("/api/instructors/upload", methods=["POST"])
@login_required
def api_instructors_upload():
    """آپلود اکسل اساتید."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "فایل ارسال نشده"}), 400
    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"ok": False, "error": "فرمت فایل باید اکسل باشد"}), 400
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        f.save(tmp.name)
        result = instructors_module.import_instructors_excel(db, tmp.name)
        os.unlink(tmp.name)
    audit_log("instructor_upload", description=f"آپلود اکسل اساتید: {result.get('count', 0)} رکورد")
    return jsonify(result)


@app.route("/api/instructors/sync", methods=["POST"])
@login_required
def api_instructors_sync():
    """همگام‌سازی اساتید از سامانه برنامه‌ریزی (پورت 8083)."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    settings = instructors_module.load_sync_settings()
    # اگر enabled نبود یا username/password خالی بود، از مقادیر پیش‌فرض استفاده کن
    if not settings.get("enabled"):
        return jsonify({
            "ok": False,
            "error": "sync_disabled",
            "message": "همگام‌سازی غیرفعال است. از مودال تنظیمات، گزینه «فعال‌سازی همگام‌سازی» را تیک بزنید و ذخیره کنید."
        })
    if not settings.get("service_url") or not settings.get("username") or not settings.get("password"):
        return jsonify({
            "ok": False,
            "error": "config_incomplete",
            "message": "تنظیمات ناقص است. service_url، username و password را در مودال تنظیمات پر کنید."
        })
    result = instructors_module.sync_instructors_from_remote(db, settings)
    if result.get("ok"):
        audit_log("instructor_sync", description=result.get("message", ""))
    return jsonify(result)


@app.route("/api/instructors/sync-test", methods=["POST"])
@login_required
def api_instructors_sync_test():
    """تست مستقیم اتصال به سامانه برنامه‌ریزی (بدون ذخیره تنظیمات)."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    service_url = data.get("service_url", "http://188.212.96.235:8083")
    username = data.get("username", "admin")
    password = data.get("password", "admin123")
    # تست fetch
    remote_data, err = instructors_module.fetch_instructors_from_remote(
        service_url=service_url,
        username=username,
        password=password,
    )
    if err:
        return jsonify({
            "ok": False,
            "error": err,
            "message": f"خطا در اتصال: {err}",
            "service_url": service_url,
            "username": username,
        })
    return jsonify({
        "ok": True,
        "count": len(remote_data or []),
        "message": f"اتصال موفق. {len(remote_data or [])} استاد یافت شد.",
        "service_url": service_url,
        "username": username,
        "sample": (remote_data or [])[:2],
    })


@app.route("/api/instructors/sync-debug", methods=["POST"])
@login_required
def api_instructors_sync_debug():
    """همگام‌سازی با لاگ کامل — برای دیباگ."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    service_url = data.get("service_url", "http://188.212.96.235:8083")
    username = data.get("username", "admin")
    password = data.get("password", "admin123")
    debug_log = []
    debug_log.append(f"1. شروع sync-debug با service_url={service_url}, username={username}")
    debug_log.append("2. شروع fetch از سامانه برنامه‌ریزی...")
    remote_data, err = instructors_module.fetch_instructors_from_remote(
        service_url=service_url, username=username, password=password,
    )
    if err:
        debug_log.append(f"3. fetch خطا: {err}")
        return jsonify({"ok": False, "error": err, "debug_log": debug_log,
                        "message": f"خطا در واکشی: {err}"})
    debug_log.append(f"3. {len(remote_data or [])} استاد دریافت شد")
    if not remote_data:
        debug_log.append("4. هیچ استادی دریافت نشد")
        return jsonify({"ok": False, "error": "no_data", "debug_log": debug_log})
    debug_log.append("4. شروع ذخیره در جدول instructors...")
    try:
        instructors_module.ensure_instructors_table(db)
        debug_log.append("5. جدول instructors تضمین شد")
    except Exception as e:
        debug_log.append(f"5. خطا در migration: {e}")
        return jsonify({"ok": False, "error": str(e), "debug_log": debug_log})
    debug_log.append("6. تست INSERT مستقیم با 1 رکورد...")
    try:
        first = remote_data[0]
        code = str(first.get("code") or first.get("id") or "")
        full_name = first.get("name") or first.get("full_name") or ""
        debug_log.append(f"   code={code}, full_name={full_name}")
        existing = db.execute_query("SELECT id FROM instructors WHERE code = ?", (code,))
        debug_log.append(f"   existing query result: {existing}")
        if existing:
            debug_log.append(f"   استاد با code={code} قبلاً ثبت شده")
        else:
            # INSERT مستقیم با SQL
            sql = "INSERT INTO instructors (row_number, code, username, full_name, phone, email, \"group\", cooperation_type, max_teaching_units, role, is_active, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            params = (int(first.get("row_number") or 0), code,
                     (first.get("username") or "").lstrip("@") or code,
                     full_name, first.get("phone") or "", first.get("email", ""),
                     first.get("group") or "", first.get("cooperation_type") or "",
                     int(first.get("max_teaching_units") or 0),
                     "instructor", 1, "remote")
            try:
                result = db.execute_query(sql, params)
                debug_log.append(f"   INSERT result: {result}")
            except Exception as e2:
                debug_log.append(f"   INSERT error: {e2}")
    except Exception as e:
        debug_log.append(f"6. خطا: {e}")
    try:
        count_rows = db.execute_query("SELECT COUNT(*) AS c FROM instructors")
        final_count = count_rows[0]["c"] if count_rows else 0
        debug_log.append(f"7. تعداد نهایی در جدول: {final_count}")
    except Exception as e:
        debug_log.append(f"7. خطا در COUNT: {e}")
        final_count = -1
    return jsonify({
        "ok": True,
        "fetched": len(remote_data or []),
        "final_count": final_count,
        "debug_log": debug_log,
        "message": f"دیباگ: {len(remote_data or [])} دریافت، {final_count} در جدول"
    })


@app.route("/api/instructors/sync-to-users", methods=["POST"])
@login_required
def api_instructors_sync_to_users():
    """افزودن اساتید به جدول authorized_users با نقش instructor (نام کاربری/رمز یکسان)."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    default_password = data.get("password", "Instructor@1405")
    result = instructors_module.sync_instructors_to_users(db, default_password=default_password)
    if result.get("ok"):
        audit_log("instructor_sync_to_users", description=result.get("message", ""))
    return jsonify(result)


@app.route("/api/instructors/diagnostic")
@login_required
def api_instructors_diagnostic():
    """دیباگ: بررسی وضعیت جدول instructors."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    diag = {"ok": True, "checks": []}
    # 1. آیا جدول وجود دارد؟
    try:
        rows = db.execute_query("SELECT name FROM sqlite_master WHERE type='table' AND name='instructors'")
        if rows:
            diag["checks"].append({"check": "table_exists", "ok": True, "value": True})
        else:
            diag["checks"].append({"check": "table_exists", "ok": False, "value": False,
                                    "message": "جدول instructors وجود ندارد — migration اجرا نشده"})
            try:
                instructors_module.ensure_instructors_table(db)
                diag["checks"].append({"check": "migration_retry", "ok": True,
                                        "message": "Migration مجدداً اجرا شد"})
            except Exception as e:
                diag["checks"].append({"check": "migration_retry", "ok": False, "error": str(e)})
                return jsonify(diag)
    except Exception as e:
        diag["checks"].append({"check": "table_exists", "ok": False, "error": str(e)})
        return jsonify(diag)
    # 2. تعداد رکوردها
    try:
        count_rows = db.execute_query("SELECT COUNT(*) AS c FROM instructors")
        count = count_rows[0]["c"] if count_rows else 0
        diag["checks"].append({"check": "count", "ok": True, "value": count})
    except Exception as e:
        diag["checks"].append({"check": "count", "ok": False, "error": str(e)})
        count = 0
    # 3. نمونه رکوردها
    if count > 0:
        try:
            sample = db.execute_query("SELECT id, code, username, full_name, cooperation_type, source FROM instructors LIMIT 3")
            diag["checks"].append({"check": "sample", "ok": True,
                                    "value": [dict(r) if not isinstance(r, dict) else r for r in sample]})
        except Exception as e:
            diag["checks"].append({"check": "sample", "ok": False, "error": str(e)})
    # 4. schema
    try:
        cols = db.execute_query("PRAGMA table_info(instructors)")
        diag["checks"].append({"check": "schema", "ok": True,
                                "value": [{"name": r["name"], "type": r["type"]} for r in cols] if cols else []})
    except Exception as e:
        diag["checks"].append({"check": "schema", "ok": False, "error": str(e)})
    # 5. بررسی همه جداول دیتابیس (شاید اساتید در جدول دیگری ثبت شده باشند)
    try:
        all_tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [r["name"] for r in all_tables] if all_tables else []
        diag["checks"].append({"check": "all_tables", "ok": True, "value": table_names})
        # برای هر جدولی که ممکن است مرتبط باشد، تعداد رکوردها را بگیر
        for tname in table_names:
            if 'instructor' in tname.lower() or 'professor' in tname.lower() or 'teacher' in tname.lower():
                try:
                    tcount_rows = db.execute_query(f"SELECT COUNT(*) AS c FROM {tname}")
                    tcount = tcount_rows[0]["c"] if tcount_rows else 0
                    diag["checks"].append({"check": f"table_{tname}_count", "ok": True, "value": tcount})
                    if tcount > 0 and tname != "instructors":
                        # نمونه رکوردها از جدول دیگر
                        try:
                            other_sample = db.execute_query(f"SELECT * FROM {tname} LIMIT 2")
                            diag["checks"].append({"check": f"table_{tname}_sample", "ok": True,
                                                    "value": [dict(r) if not isinstance(r, dict) else r for r in other_sample]})
                        except Exception as e:
                            diag["checks"].append({"check": f"table_{tname}_sample", "ok": False, "error": str(e)})
                except Exception as e:
                    diag["checks"].append({"check": f"table_{tname}_count", "ok": False, "error": str(e)})
    except Exception as e:
        diag["checks"].append({"check": "all_tables", "ok": False, "error": str(e)})
    # 6. تنظیمات sync
    try:
        sync_settings = instructors_module.load_sync_settings()
        # پاک کردن password برای امنیت
        safe_settings = dict(sync_settings)
        if safe_settings.get("password"):
            safe_settings["password"] = "***"
        diag["checks"].append({"check": "sync_settings", "ok": True, "value": safe_settings})
    except Exception as e:
        diag["checks"].append({"check": "sync_settings", "ok": False, "error": str(e)})
    # 7. تست مستقیم fetch
    try:
        sync_settings = instructors_module.load_sync_settings()
        if sync_settings.get("enabled") and sync_settings.get("service_url"):
            remote_data, fetch_err = instructors_module.fetch_instructors_from_remote(
                service_url=sync_settings["service_url"],
                username=sync_settings.get("username", ""),
                password=sync_settings.get("password", ""),
            )
            if fetch_err:
                diag["checks"].append({"check": "fetch_test", "ok": False, "error": fetch_err})
            else:
                diag["checks"].append({"check": "fetch_test", "ok": True,
                                        "value": f"{len(remote_data or [])} instructors fetched"})
        else:
            diag["checks"].append({"check": "fetch_test", "ok": False,
                                    "error": "sync disabled or service_url missing"})
    except Exception as e:
        diag["checks"].append({"check": "fetch_test", "ok": False, "error": str(e)})
    return jsonify(diag)


@app.route("/api/slot-times/periods")
def api_slot_times_periods():
    """گرفتن سه بازه زمانی بزرگ (صبح، ظهر، بعدازظهر)."""
    if not PREFERENCES_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    return jsonify({"ok": True, **slot_times_module.get_time_periods()})


@app.route("/api/courses/by-group")
@admin_or_instructor_required
def api_courses_by_group():
    """گرفتن دروس یکتا گروه‌بندی‌شده بر اساس course_group."""
    rows = db.execute_query(
        """SELECT uc.unique_code AS id, uc.unique_code, uc.title, uc.course_group,
           (SELECT credits FROM courses WHERE unique_code = uc.unique_code AND credits IS NOT NULL LIMIT 1) AS credits
           FROM unique_courses uc WHERE uc.is_active = 1 ORDER BY uc.course_group, uc.title"""
    )
    items = [dict(r) if not isinstance(r, dict) else r for r in rows] if rows else []
    # گروه‌بندی
    groups = {}
    for c in items:
        g = c.get("course_group") or "بدون گروه"
        if g not in groups:
            groups[g] = []
        groups[g].append(c)
    return jsonify({"ok": True, "items": items, "groups": groups, "count": len(items)})


@app.route("/api/instructors/sync/settings")
@login_required
def api_instructors_sync_settings():
    """گرفتن تنظیمات همگام‌سازی."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    settings = instructors_module.load_sync_settings()
    # پاک کردن password برای نمایش
    safe_settings = dict(settings)
    if safe_settings.get("password"):
        safe_settings["password"] = "********"
    return jsonify({"ok": True, "settings": safe_settings})


@app.route("/api/instructors/sync/settings", methods=["POST"])
@login_required
def api_instructors_sync_settings_save():
    """ذخیره تنظیمات همگام‌سازی."""
    if not INSTRUCTORS_AVAILABLE:
        return jsonify({"ok": False, "error": "module_unavailable"}), 503
    data = request.get_json(silent=True) or {}
    settings = instructors_module.load_sync_settings()
    for k in ("enabled", "service_url", "username", "auto_sync", "sync_interval_minutes"):
        if k in data:
            settings[k] = data[k]
    # اگر password ارسال شد و "********" نبود، به‌روزرسانی کن
    if data.get("password") and data["password"] != "********":
        settings["password"] = data["password"]
    ok = instructors_module.save_sync_settings(settings)
    audit_log("instructor_sync_settings_update", description="به‌روزرسانی تنظیمات sync")
    return jsonify({"ok": ok})


@app.route("/admin/instructors")
@login_required
def admin_instructors():
    """صفحه مدیریت اساتید — ادمین کامل، استاد/مدیرگروه فقط می‌بیند."""
    if not INSTRUCTORS_AVAILABLE:
        return render_template("admin/instructors_unavailable.html", admin=g.admin)
    search = request.args.get("search", "")
    cooperation_type = request.args.get("cooperation_type", "")
    items = instructors_module.get_all_instructors(db, search=search, cooperation_type=cooperation_type)
    sync_settings = instructors_module.load_sync_settings()
    return render_template(
        "admin/instructors.html",
        instructors=items,
        sync_settings=sync_settings,
        admin=g.admin,
        search=search,
        cooperation_type=cooperation_type,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("نام کاربری و رمز عبور را وارد کنید.", "error")
            return render_template("admin/login.html")

        admin = db.get_admin_by_username(username)
        if not admin or not verify_password(password, admin["password_hash"]):
            flash("نام کاربری یا رمز عبور نادرست است.", "error")
            return render_template("admin/login.html")

        if not admin["is_active"]:
            flash("حساب شما غیرفعال است.", "error")
            return render_template("admin/login.html")

        session.permanent = True
        session["admin"] = {
            "id": admin["id"], "username": admin["username"],
            "full_name": admin["full_name"], "role": admin["role"],
        }
        db.update_admin_last_login(admin["id"])
        audit_log("login", description=f"ورود ادمین {admin['username']}")

        next_url = request.args.get("next") or url_for("admin_index")
        return redirect(next_url)

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    audit_log("logout", description="خروج ادمین")
    session.pop("admin", None)
    flash("با موفقیت خارج شدید.", "success")
    return redirect(url_for("admin_login"))


# ==================================================
# Admin Pages
# ==================================================

@app.route("/admin")
@login_required
def admin_index():
    """داشبورد اصلی ادمین"""
    total_users = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"]
    total_requests = db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"]
    participants = db.execute_query(
        "SELECT COUNT(DISTINCT user_id) AS c FROM course_requests"
    )[0]["c"]
    total_courses = db.execute_query(
        "SELECT COUNT(*) AS c FROM courses WHERE is_active=1"
    )[0]["c"]
    blocked_users = db.execute_query(
        "SELECT COUNT(*) AS c FROM authorized_users WHERE is_blocked=1"
    )[0]["c"]

    today = datetime.utcnow().strftime("%Y-%m-%d")
    today_requests = db.execute_query(
        "SELECT COUNT(*) AS c FROM course_requests WHERE DATE(created_at) = ?",
        (today,)
    )[0]["c"]

    top_courses = db.get_top_courses(10)
    daily = db.get_daily_requests(14)
    sections = db.get_section_distribution()
    student_types = db.get_student_type_distribution()
    recent = db.get_recent_activity(8)

    # آمار کانال‌های ورود (جدید)
    channel_stats = db.get_channel_stats()
    recent_logins = db.get_recent_logins(8)

    # نظرسنجی فعال
    survey = get_active_survey_info()
    all_surveys = db.get_all_surveys()

    return render_template(
        "admin/index.html",
        stats={
            "total_users": total_users,
            "total_requests": total_requests,
            "participants": participants,
            "total_courses": total_courses,
            "blocked_users": blocked_users,
            "today_requests": today_requests,
        },
        top_courses=top_courses,
        daily=daily,
        sections=sections,
        student_types=student_types,
        recent=recent,
        channel_stats=channel_stats,
        recent_logins=recent_logins,
        survey=survey,
        all_surveys=all_surveys,
        admin=g.admin,
        channel_labels=CHANNEL_LABELS,
    )


@app.route("/admin/users")
@login_required
def admin_users():
    search = request.args.get("q", "")
    page = max(1, int(request.args.get("page", 1)))
    per_page = 25
    offset = (page - 1) * per_page

    rows = db.get_all_users(limit=per_page, offset=offset, search=search or None)
    total = db.count_all_users(search or None)
    total_pages = (total + per_page - 1) // per_page

    for u in rows:
        cnt = db.execute_query(
            "SELECT COUNT(*) AS c FROM course_requests WHERE user_id = ?", (u["id"],)
        )
        u["requests_count"] = cnt[0]["c"] if cnt else 0
        # تعداد ورودها
        login_cnt = db.execute_query(
            "SELECT COUNT(*) AS c FROM login_history WHERE user_id = ?", (u["id"],)
        )
        u["login_count"] = login_cnt[0]["c"] if login_cnt else 0
        # اطمینان از وجود user_type
        if "user_type" not in u or not u.get("user_type"):
            # تعیین از روی role
            if u.get("role") == "instructor":
                u["user_type"] = "instructor"
            elif u.get("role") == "admin":
                u["user_type"] = "admin"
            elif u.get("role") == "group_admin":
                u["user_type"] = "group_admin"
            else:
                u["user_type"] = "student"

    return render_template(
        "admin/users.html",
        users=rows, search=search, page=page,
        total_pages=total_pages, total=total,
        admin=g.admin, channel_labels=CHANNEL_LABELS,
    )


@app.route("/admin/users/<int:user_id>/block", methods=["POST"])
@login_required
def admin_user_block(user_id):
    blocked = request.form.get("blocked") == "1"
    db.block_user(user_id, blocked)
    audit_log("user_block" if blocked else "user_unblock",
              "user", user_id, f"تغییر وضعیت مسدودیت کاربر #{user_id}")
    flash(f"کاربر {'مسدود' if blocked else 'رفع مسدودیت'} شد.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/history")
@login_required
def admin_user_history(user_id):
    """تاریخچه ورود یک کاربر"""
    user_rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (user_id,))
    if not user_rows:
        flash("کاربر یافت نشد.", "error")
        return redirect(url_for("admin_users"))
    user = dict(user_rows[0])
    history = db.get_user_login_history(user_id, limit=50)
    # تعداد پیشنهادها
    cnt = db.execute_query(
        "SELECT COUNT(*) AS c FROM course_requests WHERE user_id = ?", (user_id,)
    )
    requests_count = cnt[0]["c"] if cnt else 0
    user_requests = db.get_user_requests(user_id)

    return render_template(
        "admin/user_history.html",
        user=user, history=history,
        requests_count=requests_count,
        user_requests=user_requests,
        admin=g.admin, channel_labels=CHANNEL_LABELS,
    )


@app.route("/admin/login-history")
@login_required
def admin_login_history():
    """تاریخچه کامل ورودها"""
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page

    all_logins = db.get_recent_logins(limit=1000)
    total = len(all_logins)
    page_logins = all_logins[offset:offset + per_page]
    total_pages = (total + per_page - 1) // per_page

    channel_stats = db.get_channel_stats()
    timeline = db.get_login_timeline(14)

    return render_template(
        "admin/login_history.html",
        logins=page_logins,
        page=page, total_pages=total_pages, total=total,
        channel_stats=channel_stats,
        timeline=timeline,
        admin=g.admin, channel_labels=CHANNEL_LABELS,
    )


@app.route("/admin/courses")
@login_required
def admin_courses():
    # فیلترها (v2.3.0)
    search = request.args.get("q", "")
    filter_year = request.args.get("year", "")
    filter_type = request.args.get("type", "")
    filter_section = request.args.get("section", "")

    # استفاده از متد بهبودیافته با فیلتر
    courses = db.get_all_courses(
        only_active=False,
        year=int(filter_year) if filter_year else None,
        type_coures=filter_type or None,
        section=filter_section or None,
    )
    # اعمال جستجو روی عنوان
    if search:
        courses = [c for c in courses if search.lower() in c["course_title"].lower()]

    return render_template(
        "admin/courses.html",
        courses=courses, admin=g.admin,
        search=search,
        filter_year=filter_year,
        filter_type=filter_type,
        filter_section=filter_section,
    )


@app.route("/admin/courses/add", methods=["POST"])
@login_required
def admin_course_add():
    title = (request.form.get("course_title") or "").strip()
    section = request.form.get("section", "")
    year = request.form.get("year", "")
    type_coures = request.form.get("type_coures", "")
    row_number = request.form.get("row_number", "0")
    prerequisite = (request.form.get("prerequisite") or "").strip() or "-"
    corequisite = (request.form.get("corequisite") or "").strip() or "-"
    unique_code = request.form.get("unique_code", "").strip()
    theory_credits = request.form.get("theory_credits", "").strip()
    practical_credits = request.form.get("practical_credits", "").strip()
    capacity = request.form.get("capacity_estimate", "30").strip()

    if not title:
        flash("عنوان درس الزامی است.", "error")
        return redirect(url_for("admin_courses"))
    if year not in ("1394", "1403", "100"):
        flash("سال باید ۱۳۹۴، ۱۴۰۳ یا ۱۰۰ (ناپیوسته) باشد.", "error")
        return redirect(url_for("admin_courses"))

    # محاسبه credits از نظری و عملی
    theory = int(theory_credits) if theory_credits.isdigit() else None
    practical = int(practical_credits) if practical_credits.isdigit() else None
    credits = ""
    if theory:
        credits = str(theory)
        if practical:
            credits += f"+{practical}"
    elif practical:
        credits = str(practical)

    uc = int(unique_code) if unique_code.isdigit() else None
    cap = int(capacity) if capacity.isdigit() else 30

    ok = db.add_course(
        section, int(row_number or 0), title, credits,
        prerequisite, corequisite, int(year), type_coures,
        unique_code=uc, theory_credits=theory,
        practical_credits=practical, capacity_estimate=cap
    )
    if ok:
        audit_log("course_add", "course", None, f"افزودن درس: {title}")
        flash("درس اضافه شد.", "success")
    else:
        flash("خطا در افزودن.", "error")
    return redirect(url_for("admin_courses"))


@app.route("/admin/courses/update", methods=["POST"])
@login_required
def admin_course_update():
    """به‌روزرسانی درس تفکیکی (v2.3.0)"""
    course_id = request.form.get("course_id")
    if not course_id:
        flash("شناسه درس الزامی است.", "error")
        return redirect(url_for("admin_courses"))

    title = (request.form.get("course_title") or "").strip()
    section = request.form.get("section", "")
    year = request.form.get("year", "")
    type_coures = request.form.get("type_coures", "")
    prerequisite = (request.form.get("prerequisite") or "").strip() or "-"
    unique_code = request.form.get("unique_code", "").strip()
    theory_credits = request.form.get("theory_credits", "").strip()
    practical_credits = request.form.get("practical_credits", "").strip()
    capacity = request.form.get("capacity_estimate", "30").strip()
    row_number = request.form.get("row_number", "0")

    if not title:
        flash("عنوان درس الزامی است.", "error")
        return redirect(url_for("admin_courses"))
    if year not in ("1394", "1403", "100"):
        flash("سال باید ۱۳۹۴، ۱۴۰۳ یا ۱۰۰ باشد.", "error")
        return redirect(url_for("admin_courses"))

    theory = int(theory_credits) if theory_credits.isdigit() else None
    practical = int(practical_credits) if practical_credits.isdigit() else None
    credits = ""
    if theory:
        credits = str(theory)
        if practical:
            credits += f"+{practical}"
    elif practical:
        credits = str(practical)

    uc = int(unique_code) if unique_code.isdigit() else None
    cap = int(capacity) if capacity.isdigit() else 30

    ok = db.update_course(
        int(course_id), title, section, credits, prerequisite,
        int(year), type_coures,
        unique_code=uc, theory_credits=theory,
        practical_credits=practical, capacity_estimate=cap
    )
    if ok:
        audit_log("course_update", "course", course_id, f"ویرایش درس: {title}")
        flash("درس به‌روزرسانی شد.", "success")
    else:
        flash("خطا در به‌روزرسانی.", "error")
    return redirect(url_for("admin_courses"))


@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
@login_required
def admin_course_delete(course_id):
    course = db.get_course_by_id(course_id)
    db.delete_course(course_id)
    audit_log("course_delete", "course", course_id,
              f"حذف درس: {course['course_title'] if course else course_id}")
    flash("درس حذف شد.", "success")
    return redirect(url_for("admin_courses"))


# ==================================================
# Unique Courses Management (جدید v2.3.0)
# ==================================================

@app.route("/admin/unique-courses")
@login_required
def admin_unique_courses():
    """مدیریت دروس یکتا (پایه)"""
    search = request.args.get("q", "")
    courses = db.get_all_unique_courses(only_active=False, search=search or None)

    # تعداد دروس تفکیکی هر کد یکتا
    course_counts = {}
    for c in courses:
        cnt = db.execute_query(
            "SELECT COUNT(*) AS c FROM courses WHERE unique_code = ?",
            (c["unique_code"],)
        )
        course_counts[c["unique_code"]] = cnt[0]["c"] if cnt else 0

    return render_template(
        "admin/unique_courses.html",
        courses=courses, course_counts=course_counts,
        search=search, admin=g.admin
    )


@app.route("/admin/unique-courses/add", methods=["POST"])
@login_required
def admin_unique_course_add():
    unique_code = request.form.get("unique_code", "").strip()
    title = (request.form.get("title") or "").strip()
    course_group = request.form.get("course_group", "")
    capacity = request.form.get("capacity_estimate", "30").strip()
    is_active = request.form.get("is_active", "1") == "1"

    if not unique_code.isdigit() or not title:
        flash("کد یکتا (عدد) و عنوان الزامی است.", "error")
        return redirect(url_for("admin_unique_courses"))

    ok = db.add_unique_course(
        int(unique_code), title, is_active=is_active,
        course_group=course_group,
        capacity_estimate=int(capacity) if capacity.isdigit() else 30
    )
    if ok:
        audit_log("unique_course_add", "unique_course", unique_code,
                  f"افزودن درس یکتا: {title} (کد {unique_code})")
        flash("درس یکتا اضافه شد.", "success")
    else:
        flash("خطا (احتمالاً کد یکتا تکراری است).", "error")
    return redirect(url_for("admin_unique_courses"))


@app.route("/admin/unique-courses/update", methods=["POST"])
@login_required
def admin_unique_course_update():
    unique_code = request.form.get("unique_code", "").strip()
    title = (request.form.get("title") or "").strip()
    course_group = request.form.get("course_group", "")
    capacity = request.form.get("capacity_estimate", "30").strip()
    is_active = request.form.get("is_active", "1") == "1"

    if not unique_code.isdigit():
        flash("کد یکتا الزامی است.", "error")
        return redirect(url_for("admin_unique_courses"))

    db.update_unique_course(
        int(unique_code), title=title, is_active=is_active,
        course_group=course_group,
        capacity_estimate=int(capacity) if capacity.isdigit() else 30
    )
    audit_log("unique_course_update", "unique_course", unique_code,
              f"ویرایش درس یکتا: {title}")
    flash("درس یکتا به‌روزرسانی شد.", "success")
    return redirect(url_for("admin_unique_courses"))


@app.route("/admin/unique-courses/<int:code>/delete", methods=["POST"])
@login_required
def admin_unique_course_delete(code):
    ok = db.delete_unique_course(code)
    if ok:
        audit_log("unique_course_delete", "unique_course", code,
                  f"حذف درس یکتا: {code}")
        flash("درس یکتا حذف شد.", "success")
    else:
        flash("نمی‌توان حذف کرد — دروس تفکیکی به آن وابسته‌اند. ابتدا آن‌ها را حذف کنید.", "error")
    return redirect(url_for("admin_unique_courses"))


# ==================================================
# Surveys Management (جدید v2.2.0)
# ==================================================

@app.route("/admin/surveys")
@login_required
def admin_surveys():
    import secrets
    if not session.get("survey_reset_token"):
        session["survey_reset_token"] = secrets.token_urlsafe(32)
    surveys = db.get_all_surveys()
    # تعداد پیشنهاد هر نظرسنجی
    for s in surveys:
        cnt = db.execute_query(
            "SELECT COUNT(*) AS c FROM course_requests WHERE survey_id = ?", (s["id"],)
        )
        s["requests_count"] = cnt[0]["c"] if cnt else 0
        participants = db.execute_query(
            "SELECT COUNT(DISTINCT user_id) AS c FROM course_requests WHERE survey_id = ?", (s["id"],)
        )
        s["participants"] = participants[0]["c"] if participants else 0
    return render_template("admin/surveys.html", surveys=surveys, admin=g.admin)


@app.route("/admin/surveys/add", methods=["POST"])
@login_required
def admin_survey_add():
    name = (request.form.get("name") or "").strip()
    semester = (request.form.get("semester") or "").strip()
    year = request.form.get("year", "")
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    deadline = request.form.get("deadline", "")

    if not name or not semester or not year:
        flash("نام، ترم و سال الزامی است.", "error")
        return redirect(url_for("admin_surveys"))

    if not year.isdigit():
        flash("سال باید عدد باشد.", "error")
        return redirect(url_for("admin_surveys"))

    db.create_survey(name, semester, int(year), start_date, end_date, deadline,
                     created_by=g.admin["id"])
    audit_log("survey_create", "survey", None, f"ساخت نظرسنجی: {name}")
    flash("نظرسنجی جدید ساخته شد (غیرفعال).", "success")
    return redirect(url_for("admin_surveys"))


@app.route("/admin/surveys/<int:survey_id>/activate", methods=["POST"])
@login_required
def admin_survey_activate(survey_id):
    db.activate_survey(survey_id)
    survey = db.get_survey_by_id(survey_id)
    audit_log("survey_activate", "survey", survey_id,
              f"فعال‌سازی نظرسنجی: {survey['name'] if survey else survey_id}")
    flash("نظرسنجی فعال شد. اکنون برای دانشجویان نمایش داده می‌شود.", "success")
    return redirect(url_for("admin_surveys"))


@app.route("/admin/surveys/<int:survey_id>/close", methods=["POST"])
@login_required
def admin_survey_close(survey_id):
    db.close_survey(survey_id)
    audit_log("survey_close", "survey", survey_id, f"بستن نظرسنجی #{survey_id}")
    flash("نظرسنجی بسته شد.", "success")
    return redirect(url_for("admin_surveys"))


@app.route("/admin/surveys/<int:survey_id>/delete", methods=["POST"])
@login_required
def admin_survey_delete(survey_id):
    ok = db.delete_survey(survey_id)
    if ok:
        audit_log("survey_delete", "survey", survey_id, f"حذف نظرسنجی #{survey_id}")
        flash("نظرسنجی حذف شد.", "success")
    else:
        flash("نمی‌توان نظرسنجی با پیشنهاد ثبت‌شده را حذف کرد.", "error")
    return redirect(url_for("admin_surveys"))



# SURVEY_RESPONSE_RESET_V1
@app.route("/admin/surveys/<int:survey_id>/reset-responses", methods=["POST"])
@super_admin_required
def admin_survey_reset_responses(survey_id):
    import secrets
    import sqlite3
    import uuid

    token = request.form.get("reset_token", "")
    expected = session.get("survey_reset_token", "")
    if not expected or not secrets.compare_digest(
        token.encode("utf-8"), expected.encode("utf-8")
    ):
        flash("اعتبار درخواست منقضی شده است؛ صفحه را تازه کنید.", "error")
        return redirect(url_for("admin_surveys"))

    if request.form.get("confirm_survey_id") != str(survey_id):
        flash("تأیید نظرسنجی صحیح نیست.", "error")
        return redirect(url_for("admin_surveys"))

    survey = db.get_survey_by_id(survey_id)
    if not survey:
        flash("نظرسنجی پیدا نشد.", "error")
        return redirect(url_for("admin_surveys"))

    if survey["is_active"]:
        flash("ابتدا نظرسنجی را ببندید، سپس پاسخ‌ها را پاک کنید.", "error")
        return redirect(url_for("admin_surveys"))

    conn = None
    backup_path = None
    try:
        backup_dir = os.path.join(
            os.path.dirname(os.path.abspath(db.db_path)),
            "response_reset_backups"
        )
        os.makedirs(backup_dir, exist_ok=True)
        backup_name = (
            f"before_reset_survey_{survey_id}_"
            f"{datetime.utcnow():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.sqlite3"
        )
        backup_path = os.path.join(backup_dir, backup_name)

        conn = db.get_connection()
        # SQLite backup includes committed data in WAL.
        with sqlite3.connect(backup_path) as destination:
            conn.backup(destination)

        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT is_active FROM surveys WHERE id = ?", (survey_id,)
        ).fetchone()

        if current is None or current["is_active"]:
            raise RuntimeError("Survey missing or activated during reset")

        participants = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM course_requests WHERE survey_id = ?",
            (survey_id,)
        ).fetchone()[0]

        cursor = conn.execute(
            "DELETE FROM course_requests WHERE survey_id = ?", (survey_id,)
        )
        deleted = cursor.rowcount
        conn.commit()

    except Exception:
        if conn is not None:
            conn.rollback()
        app.logger.exception("Survey response reset failed: %s", survey_id)
        flash("پاک‌کردن انجام نشد؛ خطا در لاگ سرور ثبت شد.", "error")
        return redirect(url_for("admin_surveys"))

    finally:
        if conn is not None:
            conn.close()

    session["survey_reset_token"] = secrets.token_urlsafe(32)
    audit_log(
        "survey_reset_responses", "survey", survey_id,
        f"Deleted {deleted} requests; {participants} participants; backup: {backup_path}"
    )
    flash(
        f"{deleted} پیشنهاد از {participants} شرکت‌کننده پاک شد. "
        "پشتیبان دیتابیس ذخیره شد.",
        "success"
    )
    return redirect(url_for("admin_surveys"))


@app.route("/admin/reports")
@admin_or_instructor_required
def admin_reports():
    top_courses = db.get_top_courses(20)
    daily = db.get_daily_requests(30)
    sections = db.get_section_distribution()
    student_types = db.get_student_type_distribution()
    years = db.get_year_distribution()
    return render_template(
        "admin/reports.html",
        top_courses=top_courses, daily=daily,
        sections=sections, student_types=student_types, years=years,
        admin=g.admin,
    )


@app.route("/admin/reports/excel")
@login_required
def admin_report_excel():
    results = db.execute_query("""
        SELECT u.name, u.student_number, u.student_type,
               c.course_title, c.section, c.credits, c.year,
               cr.created_at, cr.channel
        FROM course_requests cr
        JOIN authorized_users u ON cr.user_id = u.id
        LEFT JOIN courses c ON cr.id_courses = c.id
        ORDER BY cr.created_at DESC
    """)
    if not results:
        flash("داده‌ای برای گزارش وجود ندارد.", "error")
        return redirect(url_for("admin_reports"))

    import pandas as pd
    from openpyxl import load_workbook
    from openpyxl.chart import BarChart, Reference
    from openpyxl.styles import Font, PatternFill, Alignment

    df = pd.DataFrame([dict(r) for r in results])
    summary_df = df.groupby("course_title").size().reset_index(name="تعداد")
    summary_df = summary_df.sort_values("تعداد", ascending=False).head(30)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="داده_خام", index=False)
        summary_df.to_excel(writer, sheet_name="خلاصه", index=False)

    output.seek(0)
    wb = load_workbook(output)

    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

    ws_chart = wb["خلاصه"]
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = f"نمودار دروس پرتقاضا — نظرسنجی فعال"
    chart.y_axis.title = "تعداد"
    chart.x_axis.title = "درس"
    chart.height = 14
    chart.width = 26
    data = Reference(ws_chart, min_col=2, min_row=1, max_row=ws_chart.max_row)
    cats = Reference(ws_chart, min_col=1, min_row=2, max_row=ws_chart.max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    ws_chart.add_chart(chart, "D2")

    final = io.BytesIO()
    wb.save(final)
    final.seek(0)

    audit_log("report_excel", "report", None, "دانلود گزارش اکسل")

    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    resp = make_response(final.read())
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return resp


@app.route("/admin/audit-log")
@login_required
def admin_audit_log():
    action = request.args.get("action")
    logs = db.get_audit_logs(limit=200, action=action)
    return render_template("admin/audit_log.html", logs=logs, action=action, admin=g.admin)


@app.route("/admin/settings")
@login_required
def admin_settings():
    settings = {}
    rows = db.execute_query("SELECT * FROM system_settings")
    if rows:
        for r in rows:
            settings[r["key"]] = r["value"]
    return render_template("admin/settings.html", settings=settings, admin=g.admin)


@app.route("/admin/settings", methods=["POST"])
@login_required
def admin_settings_save():
    for key in ["survey_title", "welcome_message", "contact_email"]:
        value = request.form.get(key)
        if value is not None:
            db.set_setting(key, value, g.admin["id"])
    audit_log("settings_update", description="به‌روزرسانی تنظیمات")
    flash("تنظیمات ذخیره شد.", "success")
    return redirect(url_for("admin_settings"))


@app.route("/admin/admins")
@super_admin_required
def admin_admins():
    admins = db.get_all_admins()
    return render_template("admin/admins.html", admins=admins, admin=g.admin)


@app.route("/admin/admins/add", methods=["POST"])
@super_admin_required
def admin_admin_add():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    full_name = (request.form.get("full_name") or "").strip()
    email = (request.form.get("email") or "").strip()
    role = request.form.get("role", "admin")

    if not username or not password:
        flash("نام کاربری و رمز عبور الزامی است.", "error")
        return redirect(url_for("admin_admins"))
    if role not in ("admin", "super_admin", "viewer"):
        role = "admin"

    ok = db.create_admin(username, password, full_name, email, role)
    if ok:
        audit_log("admin_add", "admin", None, f"افزودن ادمین: {username}")
        flash("ادمین اضافه شد.", "success")
    else:
        flash("خطا (احتمالاً نام کاربری تکراری).", "error")
    return redirect(url_for("admin_admins"))


@app.route("/admin/admins/<int:admin_id>/toggle", methods=["POST"])
@super_admin_required
def admin_admin_toggle(admin_id):
    db.toggle_admin_active(admin_id)
    audit_log("admin_toggle", "admin", admin_id, f"تغییر وضعیت ادمین #{admin_id}")
    flash("وضعیت تغییر کرد.", "success")
    return redirect(url_for("admin_admins"))


@app.route("/admin/admins/<int:admin_id>/delete", methods=["POST"])
@super_admin_required
def admin_admin_delete(admin_id):
    if admin_id == g.admin["id"]:
        flash("نمی‌توانید خودتان را حذف کنید.", "error")
        return redirect(url_for("admin_admins"))
    ok = db.delete_admin(admin_id)
    if ok:
        audit_log("admin_delete", "admin", admin_id, f"حذف ادمین #{admin_id}")
        flash("ادمین حذف شد.", "success")
    else:
        flash("نمی‌توان آخرین super_admin را حذف کرد.", "error")
    return redirect(url_for("admin_admins"))


@app.route("/admin/profile", methods=["GET", "POST"])
@admin_or_instructor_required
def admin_profile():
    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        email = request.form.get("email", "")
        new_password = request.form.get("new_password", "")

        # اگر استاد است، در authorized_users به‌روزرسانی کن
        if g.admin.get("role") == "instructor":
            try:
                db.execute_query("UPDATE authorized_users SET name = ? WHERE id = ?", (full_name, g.admin["id"]))
                if new_password:
                    from src.database import hash_password
                    pw_hash = hash_password(new_password)
                    db.execute_query("UPDATE authorized_users SET password_hash = ? WHERE id = ?", (pw_hash, g.admin["id"]))
                # به‌روزرسانی session
                session["admin"]["full_name"] = full_name
                flash("پروفایل به‌روز شد.", "success")
            except Exception as e:
                flash(f"خطا در به‌روزرسانی: {e}", "error")
        else:
            # ادمین: از روش قبلی استفاده کن
            db.update_admin_profile(g.admin["id"], full_name=full_name, email=email)
            if new_password:
                db.update_admin_password(g.admin["id"], new_password)
            audit_log("profile_update", "admin", g.admin["id"], "به‌روزرسانی پروفایل")
            flash("پروفایل به‌روز شد.", "success")
        return redirect(url_for("admin_profile"))

    # گرفتن اطلاعات کاربر
    if g.admin.get("role") == "instructor":
        # استاد: از authorized_users
        rows = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (g.admin["id"],))
        if rows:
            admin = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
            admin["full_name"] = admin.get("name", "")
            admin["email"] = admin.get("email", "")
            admin["username"] = admin.get("student_number", "")
        else:
            admin = {"full_name": "", "email": "", "username": ""}
    else:
        # ادمین: از admin_users
        admin = db.get_admin_by_id(g.admin["id"])
    return render_template("admin/profile.html", admin=admin)


@app.route("/instructor/change-password", methods=["GET", "POST"])
@instructor_login_required
def instructor_change_password():
    """تغییر رمز عبور استاد."""
    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not old_password or not new_password:
            flash("رمز فعلی و رمز جدید را وارد کنید.", "error")
            return render_template("instructor/change_password.html")

        if len(new_password) < 4:
            flash("رمز جدید باید حداقل ۴ کاراکتر باشد.", "error")
            return render_template("instructor/change_password.html")

        if new_password != confirm_password:
            flash("رمز جدید و تأییدیه آن یکسان نیستند.", "error")
            return render_template("instructor/change_password.html")

        # بررسی رمز فعلی
        rows = db.execute_query("SELECT password_hash FROM authorized_users WHERE id = ?", (g.admin["id"],))
        if not rows:
            flash("کاربر یافت نشد.", "error")
            return render_template("instructor/change_password.html")

        user = dict(rows[0]) if not isinstance(rows[0], dict) else rows[0]
        if not verify_password(old_password, user["password_hash"]):
            flash("رمز فعلی نادرست است.", "error")
            return render_template("instructor/change_password.html")

        # به‌روزرسانی رمز
        from src.database import hash_password
        pw_hash = hash_password(new_password)
        db.execute_query("UPDATE authorized_users SET password_hash = ? WHERE id = ?", (pw_hash, g.admin["id"]))
        flash("رمز عبور با موفقیت تغییر کرد.", "success")
        return redirect(url_for("admin_preferences"))

    return render_template("instructor/change_password.html")


# ==================================================
# Mobile App (دانشجو360 — PWA) — جدید v2.6.0
# ==================================================

@app.route("/app")
def mobile_app_index():
    """صفحه اصلی موبایل اپلیکیشن دانشجو360"""
    survey = get_active_survey_info()
    stats = get_public_stats()
    return render_template(
        "mobile/index.html",
        survey=survey,
        stats=stats,
    )


@app.route("/app/dashboard")
def mobile_app_dashboard():
    """داشبورد موبایل"""
    survey = get_active_survey_info()
    stats = get_public_stats()
    return render_template(
        "mobile/dashboard.html",
        survey=survey,
        stats=stats,
    )


@app.route("/app/courses")
def mobile_app_courses():
    """فهرست دروس موبایل"""
    all_courses = db.get_all_courses(only_active=True)
    return render_template("mobile/courses.html", courses=all_courses)


@app.route("/app/login")
def mobile_app_login():
    """ورود دانشجو از موبایل"""
    return render_template("mobile/login.html")


@app.route("/app/register")
def mobile_app_register():
    """ثبت‌نام دانشجو از موبایل"""
    return render_template("mobile/register.html")


@app.route("/app/about")
def mobile_app_about():
    """درباره اپ"""
    return render_template("mobile/about.html")


# PWA Manifest
@app.route("/app/manifest.json")
def mobile_app_manifest():
    """PWA manifest برای نصب اپلیکیشن روی صفحه اصلی موبایل"""
    manifest = {
        "name": MOBILE_APP_NAME,
        "short_name": MOBILE_APP_NAME,
        "description": "سامانه نظرسنجی دروس — دانشجو360",
        "start_url": "/app",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0a0a1a",
        "theme_color": "#0f0c29",
        "lang": "fa",
        "dir": "rtl",
        "icons": [
            {
                "src": "/app/icon/192",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/app/icon/512",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ],
        "categories": ["education", "productivity"],
        "version": MOBILE_APP_VERSION,
    }
    return jsonify(manifest)


# آیکون موبایل (SVG-based, dynamically generated)
@app.route("/app/icon/<size>")
def mobile_app_icon(size):
    """تولید آیکون SVG با اندازه دلخواه"""
    try:
        s = int(size)
    except (ValueError, TypeError):
        s = 192
    # آیکون SVG با لوگو دانشجو360
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0f0c29"/>
      <stop offset="50%" style="stop-color:#302b63"/>
      <stop offset="100%" style="stop-color:#24243e"/>
    </linearGradient>
    <linearGradient id="logo" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#a78bfa"/>
      <stop offset="100%" style="stop-color:#f472b6"/>
    </linearGradient>
  </defs>
  <rect width="{s}" height="{s}" fill="url(#bg)" rx="{s*0.22}"/>
  <circle cx="{s/2}" cy="{s/2}" r="{s*0.36}" fill="url(#logo)" opacity="0.2"/>
  <g transform="translate({s/2}, {s/2})">
    <path d="M 0 -{s*0.22} L {s*0.22} -{s*0.08} L {s*0.22} {s*0.08} L 0 {s*0.22} L -{s*0.22} {s*0.08} L -{s*0.22} -{s*0.08} Z"
          fill="url(#logo)" stroke="white" stroke-width="{s*0.012}" stroke-linejoin="round"/>
    <text x="0" y="{s*0.04}" text-anchor="middle"
          font-family="Vazirmatn, sans-serif" font-size="{s*0.16}" font-weight="bold" fill="white">۳۶۰</text>
  </g>
</svg>"""
    from flask import Response
    return Response(svg, mimetype="image/svg+xml")


@app.route("/app/sw.js")
def mobile_app_service_worker():
    """Service Worker برای PWA (offline support)"""
    from flask import Response
    sw_js = """
const CACHE_NAME = 'daneshjoo360-v1';
const ASSETS = ['/app', '/app/dashboard', '/app/courses', '/app/login', '/app/register'];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
        ))
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request).then((response) => {
                if (response && response.status === 200 && response.type === 'basic') {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
                }
                return response;
            }).catch(() => cached);
        })
    );
});
"""
    return Response(sw_js, mimetype="application/javascript")


# Static files for mobile app
@app.route("/static/mobile/<path:path>")
def serve_mobile_static(path):
    return send_from_directory("static/mobile", path)


# ==================================================
# Static
# ==================================================

@app.route("/static/website/<path:path>")
def serve_static(path):
    return send_from_directory("static/website", path)


@app.route("/static/admin/<path:path>")
def serve_admin_static(path):
    return send_from_directory("static/admin", path)


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    survey = get_active_survey_info()
    print("=" * 60)
    print(f"  Public Website + Admin Panel v{APP_VERSION}")
    print(f"  Active Survey: {survey['name']}")
    print(f"  Deadline: {survey['deadline']}")
    print(f"  Website: {WEBSITE_URL}")
    print(f"  Mini App: {WEB_APP_URL}")
    print(f"  Mobile App: {MOBILE_APP_URL}")
    print(f"  Admin Login: admin / {DEFAULT_ADMIN_PASSWORD}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=WEBSITE_PORT, debug=False, use_reloader=False)
