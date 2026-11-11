# -*- coding: utf-8 -*-
"""
تست انتها-به-انتهای API مینی‌اپ (روی سرور تست با کپی دیتابیس)

اجرای سرور تست (پورت 5010، دیتابیس کپی):
    set COURSES_DB_PATH=data/test_copy.db   (ویندوز)
    python -c "import miniapp; miniapp.app.run(port=5010)"

سپس:
    python test_miniapp_api.py
"""

import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5010"
TOKEN = "2040145005:aNWlFXY4Nc2XMk-N-1brdwBuI4P9QNWgk5Y"
DB_COPY = "data/test_copy.db"

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def make_init_data(user_id, first_name="کاربر تست"):
    user = json.dumps({"id": user_id, "first_name": first_name}, ensure_ascii=False)
    pairs = {"auth_date": str(int(time.time())), "query_id": "AAF", "user": user}
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    h = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs) + "&hash=" + h


def call(path, init_data, payload=None, expect_json=True):
    body = json.dumps({"initData": init_data, **(payload or {})}).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def reset_copy():
    """کپی دیتابیس تستی: ادمین‌های موجود تنزل و شماره‌شان تغییر می‌یابد"""
    conn = sqlite3.connect(DB_COPY)
    conn.execute("UPDATE authorized_users SET role='user' WHERE role='admin'")
    conn.execute(
        "UPDATE authorized_users SET student_number = printf('%09d', 800000000 + id) "
        "WHERE student_number = '000000000'"
    )
    conn.commit()
    conn.close()


def main():
    reset_copy()
    passed, failed = [], []

    def check(name, cond, extra=""):
        (passed if cond else failed).append(name + (f" | {extra}" if extra and not cond else ""))
        print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{extra}]" if extra and not cond else ""))

    print("=== تست مینی‌اپ ===")

    # ---------- احراز هویت کاربر جدید ----------
    uid = 99001
    ida = make_init_data(uid)

    st, r = call("/api/auth", ida)
    check("auth: کاربر جدید", r.get("ok") and r.get("registered") is False, str(r))

    st, r = call("/api/contact", ida, {"phone": "۰۹۱۲۰۰۰۰۰۰۱"})
    check("contact: ثبت شماره فارسی", r.get("ok"), str(r))

    st, r = call("/api/complete-registration", ida, {
        "name": "دانشجوی تست",
        "student_number": "403999999",
        "student_type": "پیوسته",
    })
    check("register: ثبت‌نام دانشجوی 1403", r.get("ok") and not r.get("is_admin"), str(r))

    st, r = call("/api/courses", ida)
    courses = r.get("courses", [])
    check("courses: لیست دروس پیوسته 1403", r.get("ok") and len(courses) > 0,
          f"count={len(courses)}")

    if courses:
        ids = [c["id"] for c in courses[:3]]
        st, r = call("/api/submit", ida, {"courseIds": ids})
        check("submit: ثبت ۳ درس", r.get("ok") and r.get("count") == 3, str(r))

        st, r = call("/api/submit", ida, {"courseIds": ids})
        check("submit: جلوگیری از ثبت مجدد", r.get("ok") is False, str(r))

    st, r = call("/api/admin/stats", ida)
    check("admin: دسترسی دانشجو به آمار مسدود", r.get("ok") is False, str(r))

    # ---------- ادمین ----------
    admin_id = 99002
    ida_admin = make_init_data(admin_id, "ادمین تست")

    call("/api/contact", ida_admin, {"phone": "09120000002"})
    st, r = call("/api/complete-registration", ida_admin, {
        "name": "مدیر سامانه",
        "student_number": "000000000",
        "student_type": "پیوسته",
    })
    check("admin: ثبت‌نام با شماره ویژه", r.get("ok") and r.get("is_admin"), str(r))

    st, r = call("/api/admin/stats", ida_admin)
    check("admin: آمار", r.get("ok") and "stats" in r, str(r)[:120])

    st, r = call("/api/admin/courses", ida_admin)
    check("admin: لیست دروس", r.get("ok") and len(r.get("courses", [])) > 0, str(r)[:120])

    st, r = call("/api/admin/courses/add", ida_admin, {
        "course_title": "درس تست مینی‌اپ",
        "section": "basic",
        "year": "1403",
        "type_coures": "پیوسته",
        "credits": "3",
        "prerequisite": "-",
        "row_number": "999",
    })
    check("admin: افزودن درس", r.get("ok"), str(r))

    st, r = call("/api/admin/courses", ida_admin)
    added = next((c for c in r.get("courses", []) if c["title"] == "درس تست مینی‌اپ"), None)
    check("admin: درس اضافه‌شده در لیست", added is not None)

    if added:
        st, r = call("/api/admin/courses/delete", ida_admin, {"id": added["id"]})
        check("admin: حذف درس تستی", r.get("ok"), str(r))

    st, r = call("/api/admin/users", ida_admin)
    check("admin: لیست کاربران", r.get("ok") and len(r.get("users", [])) >= 2, str(r)[:120])

    # ---------- امنیت ----------
    st, r = call("/api/auth", "user=%7B%7D&hash=deadbeef")
    check("security: initData جعلی رد شود", r.get("ok") is False, str(r))

    # ---------- خروجی اکسل ----------
    req = urllib.request.Request(
        BASE + "/api/admin/report-excel",
        data=json.dumps({"initData": ida_admin}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            check("excel: گزارش اکسل تولید شد",
                  resp.status == 200 and len(data) > 1000 and data[:2] == b"PK",
                  f"status={resp.status} size={len(data)}")
    except urllib.error.HTTPError as e:
        check("excel: گزارش اکسل تولید شد", False, f"HTTP {e.code}")

    print()
    print(f"نتیجه: {len(passed)} موفق، {len(failed)} ناموفق")
    if failed:
        print("موارد ناموفق:")
        for f in failed:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
