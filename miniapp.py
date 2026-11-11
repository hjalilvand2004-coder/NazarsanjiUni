"""
miniapp.py — نسخه ۳.۵.۰ (Fixed)
مینی‌اپ بله برای «نظرسنجی پیشنهاد دروس»
"""

import io
import json
import logging
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, render_template, request, jsonify, make_response, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from src.config import (
    DB_PATH, MAX_COURSES_PER_USER, WEB_APP_URL,
    APP_VERSION, WEBSITE_URL, SECRET_KEY, ADMIN_SESSION_TTL,
    CHANNEL_MINIAPP
)
from src.database import Database, hash_password, verify_password
from src import helpers

import sys
if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config["JSON_AS_ASCII"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.config["SECRET_KEY"] = SECRET_KEY
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=ADMIN_SESSION_TTL)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

db = Database()


def get_active_survey_info():
    s = db.get_active_survey()
    if not s:
        return {"id": None, "name": "بدون نظرسنجی فعال", "semester": "—", "year": "—", "deadline": "—", "start_date": None, "end_date": None}
    return {"id": s["id"], "name": s["name"], "semester": s.get("semester", "—"), "year": s.get("year", "—"), "deadline": s.get("deadline", "—"), "start_date": s.get("start_date"), "end_date": s.get("end_date")}

def semester_label():
    return get_active_survey_info()["name"]

def survey_deadline():
    return get_active_survey_info()["deadline"]

def fail(message, status=400):
    return jsonify({"ok": False, "message": message}), status

def current_user():
    init_data = request.headers.get("X-Auth-Data", "")
    if not init_data:
        data = request.get_json(silent=True) or {}
        init_data = data.get("initData", "")
    if not init_data:
        return None, None
    valid, bale_user = helpers.validate_init_data(init_data)
    if not valid or not bale_user:
        return None, None
    bale_id = bale_user.get("id")
    if not bale_id:
        return None, None
    rows = db.execute_query("SELECT * FROM authorized_users WHERE bale_id = ?", (bale_id,))
    user = dict(rows[0]) if rows else None
    if user:
        db.update_last_seen(user["id"])
    return user, bale_user

def course_payload(c):
    return {"id": c["id"], "title": c["course_title"], "section": c.get("section") or "", "section_label": helpers.SECTION_LABELS.get(c.get("section"), c.get("section") or ""), "credits": c.get("credits") or "", "prerequisite": c.get("prerequisite") or "", "corequisite": c.get("corequisite") or "", "year": c.get("year"), "row_number": c.get("row_number"), "type": c.get("type_coures") or "", "is_active": bool(c.get("is_active", 1))}

def get_user_requests(user_id):
    rows = db.execute_query("SELECT id_courses FROM course_requests WHERE user_id = ?", (user_id,))
    return [r["id_courses"] for r in rows] if rows else []

def audit_log(admin_user, action, target_type=None, target_id=None, description=None):
    try:
        db.add_audit_log(admin_id=admin_user["id"], admin_username=admin_user["username"], action=action, target_type=target_type, target_id=target_id, description=description, ip_address=request.remote_addr if request else None)
    except Exception as e:
        print(f"audit_log error: {e}")


@app.route("/api/health")
def api_health():
    survey = get_active_survey_info()
    return jsonify({"ok": True, "version": APP_VERSION, "semester": survey["name"], "survey_id": survey["id"], "deadline": survey["deadline"], "server_time": datetime.utcnow().isoformat()})

@app.route("/api/active-survey")
def api_active_survey():
    survey = get_active_survey_info()
    return jsonify({"ok": True, "survey": survey, "version": APP_VERSION})

@app.route("/api/public/stats")
def api_public_stats():
    total_users = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"]
    total_requests = db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"]
    participants = db.execute_query("SELECT COUNT(DISTINCT user_id) AS c FROM course_requests")[0]["c"]
    total_courses = db.execute_query("SELECT COUNT(*) AS c FROM courses WHERE is_active=1")[0]["c"]
    top_rows = db.get_top_courses(10)
    return jsonify({"ok": True, "semester": semester_label(), "version": APP_VERSION, "stats": {"total_users": total_users, "total_requests": total_requests, "participants": participants, "total_courses": total_courses, "deadline": survey_deadline()}, "top_courses": [{"title": r["title"], "count": r["cnt"]} for r in top_rows]})


@app.route("/api/auth", methods=["POST"])
def api_auth():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    logger.info("AUTH request - initData length: %s", len(init_data))
    
    valid, bale_user = helpers.validate_init_data(init_data)
    if not valid:
        logger.warning("AUTH FAILED: validation returned False")
        return fail("اعتبارسنجی داده‌های ورودی ناموفق بود.", 401)
    if not bale_user:
        logger.warning("AUTH FAILED: no user data")
        return fail("اطلاعات کاربر در داده‌های ورودی یافت نشد.", 401)
    
    bale_id = bale_user.get("id")
    rows = db.execute_query("SELECT * FROM authorized_users WHERE bale_id = ?", (bale_id,))
    user = dict(rows[0]) if rows else None
    if user and user.get("is_blocked"):
        return fail("حساب کاربری شما مسدود شده است.", 403)
    
    sn = (user or {}).get("student_number") or ""
    stype = (user or {}).get("student_type") or ""
    registered = bool(user) and bool(sn) and bool(stype)
    
    if user:
        try:
            db.record_login(user["id"], CHANNEL_MINIAPP, ip_address=request.remote_addr, user_agent=request.headers.get("User-Agent", "")[:200])
        except Exception as e:
            print(f"record_login error: {e}")
    
    survey = get_active_survey_info()
    return jsonify({"ok": True, "account_exists": bool(user), "registered": registered, "is_admin": bool(user and user["role"] == "admin" and registered), "has_submitted": bool(user and db.has_user_submitted_courses(user["id"], survey["id"])), "user": {"name": user["name"] if user else bale_user.get("first_name", ""), "student_number": sn if registered else None, "student_type": user["student_type"] if user else None, "bale_id": bale_id, "bale_first_name": bale_user.get("first_name", ""), "bale_username": bale_user.get("username"), "avatar": helpers.avatar_base64(bale_id), "created_at": user["created_at"] if user else None}, "semester": survey["name"], "deadline": survey["deadline"], "survey_id": survey["id"], "version": APP_VERSION})


@app.route("/api/contact", methods=["POST"])
def api_contact():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    phone = data.get("phone", "")
    logger.info("CONTACT request - phone: %s, initData length: %s", phone[:4]+"****" if phone else "EMPTY", len(init_data))
    
    valid, bale_user = helpers.validate_init_data(init_data)
    if not valid or not bale_user:
        logger.warning("CONTACT FAILED: validation returned False")
        return fail("اعتبارسنجی ناموفق بود.", 401)
    
    phone = helpers.normalize_phone(phone)
    if not phone.startswith("09") or len(phone) != 11:
        return fail("شماره تماس معتبر نیست.")
    
    bale_id = bale_user.get("id")
    rows = db.execute_query("SELECT * FROM authorized_users WHERE normalized_phone = ? OR bale_id = ?", (phone, bale_id))
    existing = dict(rows[0]) if rows else None
    
    if existing:
        if existing.get("is_blocked"):
            return fail("حساب کاربری شما مسدود شده است.", 403)
        db.execute_query("UPDATE authorized_users SET bale_id = ? WHERE id = ? AND (bale_id IS NULL OR bale_id != ?)", (bale_id, existing["id"], bale_id))
        rows2 = db.execute_query("SELECT * FROM authorized_users WHERE id = ?", (existing["id"],))
        user = dict(rows2[0]) if rows2 else None
    else:
        pending_sn = f"{bale_id % 1000000000:09d}" if bale_id else "000000001"
        while db.execute_query("SELECT id FROM authorized_users WHERE student_number = ?", (pending_sn,)):
            pending_sn = f"{(int(pending_sn) + 1) % 1000000000:09d}"
        db.execute_query("INSERT INTO authorized_users (name, display_phone, normalized_phone, student_number, student_type, role, bale_id) VALUES (?, ?, ?, ?, NULL, 'user', ?)", (bale_user.get("first_name", "دانشجو"), phone, phone, pending_sn, bale_id))
        rows2 = db.execute_query("SELECT * FROM authorized_users WHERE normalized_phone = ?", (phone,))
        user = dict(rows2[0]) if rows2 else None
    
    if not user:
        return fail("خطای داخلی در ثبت اطلاعات.", 500)
    
    return jsonify({"ok": True, "is_admin": user["role"] == "admin", "user": {"name": user["name"], "student_number": user["student_number"], "student_type": user["student_type"]}})


@app.route("/api/complete-registration", methods=["POST"])
def api_complete_registration():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    valid, bale_user = helpers.validate_init_data(init_data)
    if not valid or not bale_user:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا شماره تماس خود را تأیید کنید.", 403)
    name = helpers.normalize_text(data.get("name", ""))
    student_number = helpers.normalize_digits(data.get("student_number", ""))
    student_type = data.get("student_type", "")
    if not name:
        return fail("نام و نام خانوادگی را وارد کنید.")
    if len(student_number) not in (9, 14):
        return fail("شماره دانشجویی باید ۹ یا ۱۴ رقم باشد.")
    valid_sn, role_or_error = db.validate_student_number(student_number)
    if not valid_sn:
        return fail(role_or_error)
    dup = db.execute_query("SELECT id FROM authorized_users WHERE student_number = ? AND id != ?", (student_number, user["id"]))
    if dup:
        return fail("این شماره دانشجویی قبلاً ثبت شده است.")
    if student_type not in ("پیوسته", "ناپیوسته"):
        return fail("نوع کارشناسی را انتخاب کنید.")
    role = "admin" if helpers.is_admin_student_number(student_number) else "user"
    if role == "admin":
        student_type = "پیوسته"
        if db.count_admins() >= 2:
            return fail("حداکثر دو ادمین مجاز است.")
    db.execute_query("UPDATE authorized_users SET name = ?, student_number = ?, student_type = ?, role = ? WHERE id = ?", (name, student_number, student_type, role, user["id"]))
    return jsonify({"ok": True, "is_admin": role == "admin", "user": {"name": name, "student_number": student_number, "student_type": student_type}})


@app.route("/api/courses", methods=["POST"])
def api_courses():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    if user["role"] == "admin" and not user["student_type"]:
        courses = db.get_all_courses()
    else:
        courses = helpers.get_available_courses_for_user(db, user)
    # ===== [v3.6.5] ارسال لیست درس‌های مستثنا (کارآموزی/پروژه) به کلاینت =====
    EXEMPT_KEYWORDS = ("کارآموزی", "پروژه")
    exempt_ids = [c["id"] for c in courses if any(kw in (c.get("course_title") or "") for kw in EXEMPT_KEYWORDS)]
    return jsonify({
        "ok": True,
        "max": MAX_COURSES_PER_USER,
        "exempt_ids": exempt_ids,
        "exempt_keywords": list(EXEMPT_KEYWORDS),
        "courses": [course_payload(c) for c in helpers.sort_courses(courses)],
        "selected": get_user_requests(user["id"])
    })


@app.route("/api/submit", methods=["POST"])
def api_submit():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    course_ids = data.get("courseIds", [])
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    if user["role"] != "admin" and db.has_user_submitted_courses(user["id"]):
        return fail("شما قبلاً پیشنهاد خود را ثبت کرده‌اید.", 403)
    if not course_ids:
        return fail("هیچ درسی انتخاب نشده است.")
    # ===== [v3.6.5] محدودیت ۶ درس، با استثنای کارآموزی و پروژه =====
    EXEMPT_KEYWORDS = ("کارآموزی", "پروژه")
    # گرفتن عناوین دروس انتخاب‌شده برای تشخیص استثنا
    placeholders = ",".join("?" * len(course_ids))
    selected_rows = db.execute_query(
        f"SELECT id, course_title FROM courses WHERE id IN ({placeholders})",
        tuple(course_ids)
    )
    exempt_ids = set()
    for r in selected_rows:
        title = (r.get("course_title") if isinstance(r, dict) else r[1]) or ""
        if any(kw in title for kw in EXEMPT_KEYWORDS):
            exempt_ids.add(r.get("id") if isinstance(r, dict) else r[0])
    non_exempt_count = len([c for c in course_ids if c not in exempt_ids])
    if non_exempt_count > MAX_COURSES_PER_USER:
        return fail(f"حداکثر {MAX_COURSES_PER_USER} درس می‌توانید انتخاب کنید (به جز کارآموزی و پروژه).")
    if user["role"] == "admin" and not user["student_type"]:
        allowed = db.get_all_courses()
    else:
        allowed = helpers.get_available_courses_for_user(db, user)
    allowed_ids = {c["id"] for c in allowed}
    survey = get_active_survey_info()
    survey_id = survey["id"]
    success_count = 0
    for cid in course_ids:
        if cid in allowed_ids:
            if db.add_user_course(user["id"], cid, survey_id=survey_id, channel=CHANNEL_MINIAPP):
                success_count += 1
    if success_count == 0:
        return fail("ثبت پیشنهادات ناموفق بود.", 500)
    db.add_notification(user["id"], "ثبت پیشنهاد دروس", f"{success_count} درس برای ترم {semester_label()} ثبت شد.", "success")
    return jsonify({"ok": True, "count": success_count})


@app.route("/api/dashboard", methods=["POST"])
def api_dashboard():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    user_requests = db.get_user_requests(user["id"])
    total_users = db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"]
    total_requests = db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"]
    participants = db.execute_query("SELECT COUNT(DISTINCT user_id) AS c FROM course_requests")[0]["c"]
    survey = get_active_survey_info()
    return jsonify({"ok": True, "semester": survey["name"], "deadline": survey["deadline"], "survey_id": survey["id"], "user": {"name": user["name"], "student_number": user["student_number"], "student_type": user["student_type"], "is_admin": user["role"] == "admin"}, "summary": {"my_requests": len(user_requests), "max_requests": MAX_COURSES_PER_USER, "remaining": max(0, MAX_COURSES_PER_USER - len(user_requests)), "total_users": total_users, "total_requests": total_requests, "participants": participants}, "my_courses": [{"id": r["id_courses"], "title": r.get("course_title") or r["course_name"], "credits": r.get("credits"), "section": r.get("section"), "section_label": helpers.SECTION_LABELS.get(r.get("section"), ""), "submitted_at": r["created_at"]} for r in user_requests], "progress_pct": min(100, int((len(user_requests) / MAX_COURSES_PER_USER) * 100))})


@app.route("/api/profile", methods=["POST"])
def api_profile():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, bale_user = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    return jsonify({"ok": True, "profile": {"name": user["name"], "student_number": user["student_number"], "student_type": user["student_type"], "phone": user["display_phone"], "role": user["role"], "created_at": user["created_at"], "last_seen": user.get("last_seen"), "bale_username": (bale_user or {}).get("username"), "bale_first_name": (bale_user or {}).get("first_name"), "avatar": helpers.avatar_base64(user.get("bale_id"))}})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    course_id = data.get("course_id")
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    if not course_id:
        return fail("شناسه درس را ارسال کنید.")
    ok = db.remove_user_course(user["id"], course_id)
    if not ok:
        return fail("حذف ناموفق بود.", 500)
    db.add_notification(user["id"], "حذف پیشنهاد", "درس از فهرست پیشنهادهای شما حذف شد.", "warning")
    return jsonify({"ok": True})


@app.route("/api/notifications", methods=["POST"])
def api_notifications():
    data = request.get_json(silent=True) or {}
    init_data = data.get("initData", "")
    valid, _ = helpers.validate_init_data(init_data)
    if not valid:
        return fail("اعتبارسنجی ناموفق بود.", 401)
    user, _ = current_user()
    if not user:
        return fail("ابتدا ثبت‌نام را کامل کنید.", 403)
    notifs = db.get_user_notifications(user["id"], limit=20)
    return jsonify({"ok": True, "notifications": [{"id": n["id"], "title": n["title"], "body": n["body"], "level": n["level"], "is_read": bool(n["is_read"]), "created_at": n["created_at"]} for n in notifs]})


def require_admin():
    user, _ = current_user()
    if not user or user["role"] != "admin":
        return None, fail("دسترسی فقط برای ادمین مجاز است.", 403)
    return user, None

REPORT_QUERY = """
    SELECT COALESCE(c.year, -1) AS year, u.student_type AS student_type, COALESCE(c.course_title, cr.course_name) AS course_title, COUNT(*) AS count
    FROM course_requests cr JOIN authorized_users u ON cr.user_id = u.id LEFT JOIN courses c ON cr.id_courses = c.id
    GROUP BY COALESCE(c.year, -1), u.student_type, COALESCE(c.course_title, cr.course_name)
    ORDER BY year DESC, count DESC
"""

@app.route("/api/admin/stats", methods=["POST"])
def api_admin_stats():
    _, err = require_admin()
    if err: return err
    results = db.execute_query(REPORT_QUERY) or []
    participation = db.get_participation_stats() or []
    stats = {"total_users": db.execute_query("SELECT COUNT(*) AS c FROM authorized_users")[0]["c"], "total_requests": db.execute_query("SELECT COUNT(*) AS c FROM course_requests")[0]["c"], "participants": db.execute_query("SELECT COUNT(DISTINCT user_id) AS c FROM course_requests")[0]["c"], "total_courses": db.execute_query("SELECT COUNT(*) AS c FROM courses WHERE is_active=1")[0]["c"], "blocked_users": db.execute_query("SELECT COUNT(*) AS c FROM authorized_users WHERE is_blocked=1")[0]["c"]}
    summary = {}
    for r in results:
        title = r["course_title"]
        summary[title] = summary.get(title, 0) + r["count"]
    top_courses = sorted(summary.items(), key=lambda x: x[1], reverse=True)[:20]
    survey = get_active_survey_info()
    return jsonify({"ok": True, "semester": survey["name"], "deadline": survey["deadline"], "stats": stats, "requests": [{"year": r["year"] if r["year"] != -1 else "نامشخص", "student_type": r["student_type"] or "نامشخص", "course_title": r["course_title"], "count": r["count"]} for r in results], "participation": [{"year": 100 if (r["student_type"] == "ناپیوسته") else r["year_group"], "student_type": r["student_type"], "count": r["participant_count"]} for r in participation], "top_courses": [{"title": t, "count": c} for t, c in top_courses], "daily_requests": db.get_daily_requests(30), "section_distribution": db.get_section_distribution(), "student_type_distribution": db.get_student_type_distribution(), "year_distribution": db.get_year_distribution(), "recent_activity": db.get_recent_activity(10)})

@app.route("/api/admin/courses", methods=["POST"])
def api_admin_courses():
    _, err = require_admin()
    if err: return err
    courses = db.get_all_courses(only_active=False)
    return jsonify({"ok": True, "courses": [course_payload(c) for c in courses]})

@app.route("/api/admin/courses/add", methods=["POST"])
def api_admin_add_course():
    user, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    title = helpers.normalize_text(data.get("course_title", ""))
    if not title: return fail("نام درس را وارد کنید.")
    year = helpers.normalize_digits(data.get("year", ""))
    if year not in ("1394", "1403"): return fail("سال باید ۱۳۹۴ یا ۱۴۰۳ باشد.")
    row_number = helpers.normalize_digits(data.get("row_number", ""))
    if not row_number.isdigit(): return fail("شماره ردیف باید عدد باشد.")
    ok = db.add_course(section=data.get("section", ""), row_number=int(row_number), course_title=title, credits=helpers.normalize_text(data.get("credits", "")), prerequisite=helpers.normalize_text(data.get("prerequisite", "")), corequisite=helpers.normalize_text(data.get("corequisite", "")), year=int(year), type_coures=data.get("type_coures", ""))
    if not ok: return fail("خطا در ثبت درس.", 500)
    audit_log(user, "course_add", "course", None, f"افزودن درس: {title}")
    return jsonify({"ok": True})

@app.route("/api/admin/courses/update", methods=["POST"])
def api_admin_update_course():
    user, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    course_id = data.get("id")
    if not course_id: return fail("شناسه درس نامعتبر است.")
    title = helpers.normalize_text(data.get("course_title", ""))
    if not title: return fail("نام درس را وارد کنید.")
    ok = db.update_course(course_id, title, data.get("section", ""), helpers.normalize_text(data.get("credits", "")), helpers.normalize_text(data.get("prerequisite", "")), data.get("year"), data.get("type_coures", ""))
    if not ok: return fail("خطا در ویرایش درس.", 500)
    audit_log(user, "course_update", "course", course_id, f"ویرایش درس: {title}")
    return jsonify({"ok": True})

@app.route("/api/admin/courses/delete", methods=["POST"])
def api_admin_delete_course():
    user, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    course_id = data.get("id")
    if not course_id: return fail("شناسه درس نامعتبر است.")
    course = db.get_course_by_id(course_id)
    db.delete_course(course_id)
    audit_log(user, "course_delete", "course", course_id, f"حذف درس: {course['course_title'] if course else course_id}")
    return jsonify({"ok": True})

@app.route("/api/admin/users", methods=["POST"])
def api_admin_users():
    _, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    search = data.get("search", "")
    page = max(1, int(data.get("page", 1)))
    per_page = min(100, int(data.get("per_page", 50)))
    offset = (page - 1) * per_page
    rows = db.get_all_users(limit=per_page, offset=offset, search=search or None)
    total = db.count_all_users(search or None)
    users = []
    for r in rows:
        u = dict(r)
        req_count = db.execute_query("SELECT COUNT(*) AS c FROM course_requests WHERE user_id=?", (u["id"],))
        users.append({"id": u["id"], "name": u["name"], "phone": u["display_phone"], "student_number": u["student_number"], "student_type": u["student_type"], "role": u["role"], "created_at": u["created_at"], "last_seen": u.get("last_seen"), "is_blocked": bool(u.get("is_blocked", 0)), "requests_count": req_count[0]["c"] if req_count else 0})
    return jsonify({"ok": True, "users": users, "total": total, "page": page, "per_page": per_page, "total_pages": (total + per_page - 1) // per_page})

@app.route("/api/admin/users/block", methods=["POST"])
def api_admin_block_user():
    user, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    blocked = bool(data.get("blocked", True))
    if not user_id: return fail("شناسه کاربر الزامی است.")
    db.block_user(user_id, blocked)
    audit_log(user, "user_block" if blocked else "user_unblock", "user", user_id, f"تغییر وضعیت مسدودیت کاربر #{user_id}")
    return jsonify({"ok": True})

@app.route("/api/admin/audit-log", methods=["POST"])
def api_admin_audit_log():
    _, err = require_admin()
    if err: return err
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    limit = min(200, int(data.get("limit", 100)))
    logs = db.get_audit_logs(limit=limit, action=action)
    return jsonify({"ok": True, "logs": [{"id": l["id"], "admin_username": l["admin_username"], "action": l["action"], "target_type": l["target_type"], "target_id": l["target_id"], "description": l["description"], "ip_address": l["ip_address"], "created_at": l["created_at"]} for l in logs]})

@app.route("/api/admin/recent-activity", methods=["POST"])
def api_admin_recent_activity():
    _, err = require_admin()
    if err: return err
    activities = db.get_recent_activity(20)
    return jsonify({"ok": True, "activities": [{"id": a["id"], "created_at": a["created_at"], "user_name": a["name"], "student_number": a["student_number"], "course_title": a["course_title"], "section": a["section"]} for a in activities]})

EXCEL_HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
EXCEL_HEADER_FONT = Font(color="FFFFFF", bold=True)
EXCEL_CENTER = Alignment(horizontal="center", vertical="center")

def _format_excel_sheet(ws):
    ws.freeze_panes = "A2"
    for cell in ws[1]:
        cell.fill = EXCEL_HEADER_FILL
        cell.font = EXCEL_HEADER_FONT
        cell.alignment = EXCEL_CENTER
    for col_cells in ws.columns:
        max_length = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                val = str(cell.value) if cell.value is not None else ""
                max_length = max(max_length, len(val))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 40)

@app.route("/api/admin/report-excel", methods=["POST"])
def api_admin_report_excel():
    user, err = require_admin()
    if err: return err
    results = db.execute_query(REPORT_QUERY)
    if not results: return fail("هنوز هیچ پیشنهادی ثبت نشده است.", 404)
    df = pd.DataFrame([dict(r) for r in results])
    df["year"] = df["year"].apply(lambda x: "نامشخص" if x == -1 or x is None else str(x))
    df["student_type"] = df["student_type"].apply(helpers.normalize_text)
    df["course_title"] = df["course_title"].apply(helpers.normalize_text)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    raw_df = df.rename(columns={"year": "سال", "student_type": "نوع دانشجو", "course_title": "نام درس", "count": "تعداد پیشنهاد"})
    summary_df = (raw_df.groupby("نام درس", as_index=False)["تعداد پیشنهاد"].sum().sort_values(by="تعداد پیشنهاد", ascending=False))
    chart_df = summary_df.head(20).copy()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        raw_df.to_excel(writer, sheet_name="داده_خام", index=False)
        summary_df.to_excel(writer, sheet_name="خلاصه", index=False)
        chart_df.to_excel(writer, sheet_name="نمودار", index=False)
    output.seek(0)
    wb = load_workbook(output)
    for ws in wb.worksheets:
        _format_excel_sheet(ws)
    ws_chart = wb["نمودار"]
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = f"نمودار تعداد پیشنهاد هر درس — ترم {semester_label()}"
    chart.y_axis.title = "تعداد پیشنهاد"
    chart.x_axis.title = "نام درس"
    chart.height = 12
    chart.width = 22
    data = Reference(ws_chart, min_col=2, min_row=1, max_row=ws_chart.max_row)
    categories = Reference(ws_chart, min_col=1, min_row=2, max_row=ws_chart.max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    ws_chart.add_chart(chart, "D2")
    final = io.BytesIO()
    wb.save(final)
    final.seek(0)
    audit_log(user, "report_excel", "report", None, "دانلود گزارش اکسل")
    filename = f"report_behman_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    resp = make_response(final.read())
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return resp

@app.route("/")
def index():
    return render_template("miniapp.html", semester=semester_label(), version=APP_VERSION)

@app.route("/static/website/Vazir.ttf")
def serve_vazir_font():
    return send_from_directory("static/website", "Vazir.ttf")

if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    survey = get_active_survey_info()
    print("=" * 60)
    print(f"  Mini App v{APP_VERSION}")
    print(f"  Active Survey: {survey['name']}")
    print(f"  Deadline: {survey['deadline']}")
    print(f"  Server: http://0.0.0.0:5000")
    print(f"  Web URL: {WEB_APP_URL}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
