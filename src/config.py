# src/config.py
"""
تنظیمات سامانه نظرسنجی دروس — نسخه ۳.۵.۰
"""

import os

# هویت بازو
BALE_BOT_TOKEN = "2040145005:aNWlFXY4Nc2XMk-N-1brdwBuI4P9QNWgk5Y"
BALE_API_URL = f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}"
BOT_USERNAME = ""

# آدرس سرور (HTTPS الزامی برای بله)
SERVER_HOST = "darsyar360.ir"
SERVER_PORT = 5000
WEBSITE_PORT = 8082

WEB_APP_URL = "https://darsyar360.ir/miniapp/"
WEBSITE_URL = "https://darsyar360.ir"
MOBILE_APP_URL = f"{WEBSITE_URL}/app"
APK_DOWNLOAD_URL = f"{WEBSITE_URL}/download-app"

# شرکت پشتیبان
COMPANY_NAME = "شرکت ماه افزار هوشمند رسا"
COMPANY_URL = "https://MahAI.ir"

# دیتابیس
DB_PATH = os.environ.get("COURSES_DB_PATH", "data/courses_survey.db")
MAX_COURSES_PER_USER = 6
PASSING_SCORE = 60

# فایل‌های پایه اکسل
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YEKTA_COURSES_FILE = os.path.join(BASE_DIR, "data", "CourceListYekta.xlsx")
DETAIL_COURSES_FILE = os.path.join(BASE_DIR, "data", "CourceListDetail.xlsx")

# احراز هویت
SECRET_KEY = os.environ.get("SECRET_KEY", "behman-1405-survey-secret-key-v35-2c8f4a9b")
ADMIN_SESSION_TTL = 8 * 3600
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin@1405"
PASSWORD_HASH_ITERATIONS = 100000
STUDENT_SESSION_TTL = 24 * 3600

# کانال‌های ورود
CHANNEL_BOT = "bot"
CHANNEL_MINIAPP = "miniapp"
CHANNEL_WEBSITE = "website"
CHANNEL_MOBILE = "mobile"

CHANNEL_LABELS = {
    "bot": "بازوی بله",
    "miniapp": "مینی‌اپ بله",
    "website": "وب‌سایت",
    "mobile": "موبایل اپ",
}

# برچسب بخش‌های درس
SECTION_LABELS = {
    "basic": "پایه",
    "core": "اصلی",
    "specialized": "تخصصی",
    "specialized_sw": "تخصصی نرم‌افزار",
    "specialized_elective_sw": "تخصصی اختیاری نرم‌افزار",
    "specialized_ai": "تخصصی هوش",
    "Prerequisite": "پیش‌نیاز",
    "electives": "اختیاری",
}

# پیام‌های بات
MESSAGES = {
    "welcome": (
        "🎓 <b>سامانه نظرسنجی دروس</b>\n"
        "📍 دانشگاه آزاد اسلامی واحد تهران شمال\n"
        "─────────────────\n"
        "👋 سلام! برای ادامه، یکی از روش‌های زیر را انتخاب کنید:\n\n"
        "📱 <b>۱. مینی‌اپ بله</b> — رابط کاربری شیک داخل بله\n"
        "🌐 <b>۲. وب‌سایت</b> — تجربه کامل در مرورگر\n"
        "💬 <b>۳. همین بات</b> — ادامه با چت متنی\n\n"
        "{survey_status}"
    ),
    "no_active_survey": (
        "⚠️ <b>در حال حاضر نظرسنجی فعالی وجود ندارد.</b>\n"
        "لطفاً بعداً مراجعه کنید."
    ),
    "active_survey_info": (
        "📅 ترم فعال: <b>{semester}</b>\n"
        "⏰ مهلت نظرسنجی: <b>{deadline}</b>"
    ),
    "channel_chosen_miniapp": (
        "📱 <b>ورود از طریق مینی‌اپ</b>\n"
        "─────────────────\n"
        "روی دکمه «🌐 ورود به مینی‌اپ» زیر بزنید تا رابط کاربری شیک باز شود."
    ),
    "channel_chosen_website": (
        "🌐 <b>ورود از طریق وب‌سایت</b>\n"
        "─────────────────\n"
        "آدرس زیر را در مرورگر باز کنید:\n"
        "{website_url}\n\n"
        "سپس روی «ثبت‌نام / ورود» بزنید."
    ),
    "channel_chosen_bot": (
        "💬 <b>ادامه در همین بات</b>\n"
        "─────────────────\n"
        "برای شروع، شماره تماس خود را با دکمه زیر ارسال کنید."
    ),
    "auth_success": (
        "✅ <b>احراز هویت با موفقیت انجام شد</b>\n"
        "─────────────────\n"
        "👤 نام: <b>{name}</b>\n"
        "📱 شماره تماس: <code>{phone}</code>\n\n"
        "📚 فهرست دروس نمایش داده می‌شود."
    ),
    "registration_success": "✅ ثبت‌نام شما با موفقیت انجام شد.",
    "not_authorized": "❌ شما مجاز به ثبت پیشنهاد درس نیستید.",
    "send_course": "📚 لطفاً نام یا کد درس مورد نظر خود را ارسال کنید.",
    "course_saved": "✅ درس با موفقیت ثبت شد.\n\n📌 درس پیشنهادی: {course}",
    "duplicate_course": "⚠️ این درس را قبلاً ثبت کرده‌اید.",
    "limit_reached": "⚠️ شما به حداکثر تعداد دروس قابل ثبت رسیده‌اید.",
    "thanks": "🙏 از همکاری شما سپاسگزاریم.\n\n📊 برای مشاهده آمار زنده به وب‌سایت مراجعه کنید:\n{website_url}"
}

# متادیتای نسخه
APP_VERSION = "3.5.0"
APP_RELEASE_DATE = "1405-07-09"
APP_TITLE = "سامانه نظرسنجی دروس"
MOBILE_APP_NAME = "دانشجو360"
MOBILE_APP_VERSION = "1.2.0"