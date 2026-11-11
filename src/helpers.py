"""
helpers.py
توابع مشترک بین بازوی بله و مینی‌اپ:
نرمال‌سازی، اعتبارسنجی initData مینی‌اپ، فیلتر دروس و آواتار کاربر.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import urllib.request

from src.config import BALE_BOT_TOKEN

DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# برچسب فارسی بخش‌های درس (مشترک بین بازو و مینی‌اپ)
SECTION_LABELS = {
    "basic": "پایه",
    "core": "اصلی",
    "specialized": "تخصصی",
    "specialized_sw": "تخصصی نرم افزار",
    "specialized_elective_sw": "تخصصی اختیاری نرم افزار",
    "specialized_ai": "تخصصی هوش",
    "Prerequisite": "پیش نیاز",
    "electives": "اختیاری",
}


# --------------------------------------------------
# نرمال‌سازی
# --------------------------------------------------

def normalize_digits(value) -> str:
    """تبدیل اعداد فارسی/عربی به انگلیسی"""
    if value is None:
        return ""
    return str(value).translate(DIGIT_MAP).strip()


def normalize_text(value) -> str:
    if value is None:
        return ""
    return normalize_digits(str(value).strip())


def normalize_phone(phone) -> str:
    """همه شماره‌ها به فرم 09xxxxxxxxx برمی‌گردند"""
    phone = normalize_digits(str(phone)).replace(" ", "").replace("-", "")

    if phone.startswith("+98"):
        phone = "0" + phone[3:]
    if phone.startswith("98") and len(phone) >= 11:
        phone = "0" + phone[2:]

    return phone


def is_admin_student_number(student_number: str) -> bool:
    return normalize_digits(student_number) == "000000000"


def get_courses_year_by_student_number(student_number: str):
    student_number = normalize_digits(student_number)
    if not student_number:
        return None

    p2, p3 = student_number[:2], student_number[:3]

    if p2 in ("94", "95", "96", "97", "98", "99") or p3 in ("400", "401", "402"):
        return 1394
    if p3 in ("403", "404", "405"):
        return 1403
    return None


# --------------------------------------------------
# فیلتر دروس بر اساس نوع دانشجو
# --------------------------------------------------

def get_available_courses_for_user(db, user_info) -> list:
    """فهرست دروس مجاز برای یک دانشجو (همان منطق بازو)"""
    student_number = normalize_digits(user_info["student_number"])
    student_type = normalize_text(user_info["student_type"])

    courses = db.get_all_courses()

    if student_type == "ناپیوسته":
        return [
            c for c in courses
            if normalize_text(c.get("type_coures")) == "ناپیوسته"
        ]

    year = get_courses_year_by_student_number(student_number)
    if not year:
        return []

    return [
        c for c in courses
        if c["year"] == year and normalize_text(c.get("type_coures")) == "پیوسته"
    ]


def sort_courses(courses: list) -> list:
    """مرتب‌سازی استاندارد دروس برای نمایش"""
    return sorted(
        courses,
        key=lambda x: (
            x.get("section") or "",
            x["row_number"] if x.get("row_number") is not None else 9999,
            x.get("course_title") or "",
        ),
    )


# --------------------------------------------------
# اعتبارسنجی initData مینی‌اپ (طبق مستندات بله)
# --------------------------------------------------

def validate_init_data(init_data: str):
    """
    اعتبارسنجی HMAC-SHA256 داده‌های مینی‌اپ بله.
    خروجی: (valid, user_dict یا None)

    طبق مستندات بله، کلید HMAC امضای HMAC-SHA256(توکن بازو، "WebAppData") است.
    برای سازگاری، هم مقادیر دیکودشده و هم مقادیر خام بررسی می‌شوند.
    """
    try:
        received_hash = ""
        for pair in init_data.split("&"):
            key, _, value = pair.partition("=")
            if key == "hash":
                received_hash = value
                break

        if not received_hash:
            return False, None

        secret_key = hmac.new(
            b"WebAppData", BALE_BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        def _check(data_check_string: str) -> bool:
            calculated = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(calculated, received_hash)

        # روش ۱: مقادیر دیکودشده (استاندارد URL-encoded query)
        decoded = urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        decoded_items = sorted(f"{k}={v}" for k, v in decoded if k != "hash")
        decoded_ok = _check("\n".join(decoded_items))

        # روش ۲: مقادیر خام (بدون دیکود)
        raw_items = sorted(
            pair for pair in init_data.split("&")
            if not pair.startswith("hash=")
        )
        raw_ok = _check("\n".join(raw_items))

        if not (decoded_ok or raw_ok):
            return False, None

        # استخراج کاربر
        for key, value in decoded:
            if key == "user":
                return True, json.loads(value)

        return True, None

    except Exception as e:
        print(f"validate_init_data error: {e}")
        return False, None


# --------------------------------------------------
# آواتار کاربر (بدون وابستگی requests)
# --------------------------------------------------

def download_avatar(user_id: int, cache_dir: str = "static/avatars"):
    """دانلود و کش کردن عکس پروفایل کاربر بله — خروجی بایت تصویر یا None"""
    try:
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

        cache_file = os.path.join(cache_dir, f"{user_id}.png")
        if os.path.exists(cache_file):
            with open(cache_file, "rb") as f:
                return f.read()

        url = f"https://tapi.bale.ai/file/bot{BALE_BOT_TOKEN}/images/profiles/{user_id}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "MiniApp/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()

        if data:
            with open(cache_file, "wb") as f:
                f.write(data)
            return data

        return None

    except Exception:
        return None


def avatar_base64(user_id: int):
    data = download_avatar(user_id)
    if not data:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode()
