"""
slot_times.py — منبع یگانهٔ حقیقت برای روزها، ترم‌ها و اسلات‌های استاندارد
================================================================
این ماژول مستقل از دیتابیس است و فقط داده‌های مرجع را فراهم می‌کند.
"""

# ==================================================
# روزهای هفته
# ==================================================

DAY_MAP = {
    "شنبه": 0, "یکشنبه": 1, "دوشنبه": 2,
    "سه‌شنبه": 3, "سهشنبه": 3,
    "چهارشنبه": 4, "پنجشنبه": 5, "جمعه": 6,
    # معادل‌های لاتین
    "sat": 0, "sun": 1, "mon": 2, "tue": 3,
    "wed": 4, "thu": 5, "fri": 6,
    "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
    "wednesday": 4, "thursday": 5, "friday": 6,
}

DAY_NAMES_FA = {
    0: "شنبه", 1: "یکشنبه", 2: "دوشنبه",
    3: "سه‌شنبه", 4: "چهارشنبه", 5: "پنجشنبه", 6: "جمعه",
}


def normalize_day(day):
    """نرمال‌سازی نام روز — حذف فاصله/نیم‌فاصله، تبدیل ي→ی، ك→ک، case-insensitive."""
    if day is None:
        return None
    # اگر عدد بود
    if isinstance(day, int):
        return day
    s = str(day).strip()
    if s.isdigit():
        return int(s)
    # حذف نیم‌فاصله (U+200C) و فاصله‌های معمولی
    s = s.replace("\u200c", "").replace(" ", "").replace("‌", "")
    # تبدیل ي/ى به ی و ك به ک
    s = s.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    # case-insensitive
    s_lower = s.lower()
    # تطابق با DAY_MAP
    for key, val in DAY_MAP.items():
        key_norm = key.replace("\u200c", "").replace(" ", "").lower()
        if s_lower == key_norm:
            return val
    return None


def normalize_term(term):
    """نرمال‌سازی نام ترم به کلید استاندارد semester_1 / semester_2 / summer."""
    if not term:
        return "semester_1"  # پیش‌فرض
    s = str(term).strip().lower()
    s = s.replace("\u200c", "").replace(" ", "")
    # تبدیل ارقام فارسی/عربی
    persian_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    s = s.translate(persian_map)

    # نگاشت‌ها
    semester_1_keys = {"semester_1", "semester1", "first", "fall", "mehr", "مهر",
                       "نیمسالاول", "ترماول", "1", "odd"}
    semester_2_keys = {"semester_2", "semester2", "second", "spring", "bahman", "بهمن",
                      "نیمسالدوم", "ترمدوم", "2", "even"}
    summer_keys = {"summer", "تابستان", "نیمسالتابستان"}

    if s in semester_1_keys:
        return "semester_1"
    if s in semester_2_keys:
        return "semester_2"
    if s in summer_keys:
        return "summer"

    # ترم‌های عددی: فرد → semester_1، زوج → semester_2
    if "فرد" in s or "odd" in s:
        return "semester_1"
    if "زوج" in s or "even" in s:
        return "semester_2"
    # ترم‌های عددی مثل "ترم چهارم" → زوج
    if "ترم" in s and any(c.isdigit() for c in s):
        # استخراج عدد
        digits = "".join(c for c in s if c.isdigit())
        if digits:
            try:
                num = int(digits)
                if num % 2 == 1:
                    return "semester_1"
                else:
                    return "semester_2"
            except ValueError:
                pass

    # نگاشت‌های فارسی به انگلیسی
    if "اول" in s or "مهر" in s:
        return "semester_1"
    if "دوم" in s or "بهمن" in s:
        return "semester_2"
    if "تابستان" in s:
        return "summer"

    return "semester_1"  # پیش‌فرض ایمن


# ==================================================
# اسلات‌های استاندارد
# ==================================================

SLOTS = {
    "semester_1": {
        1: [  # یک واحدی (به‌ندرت استفاده)
            ("07:30-09:15", "07:30", "09:15", "morning", "صبح"),
            ("09:16-11:00", "09:16", "11:00", "morning", "صبح"),
            ("11:01-12:45", "11:01", "12:45", "morning", "صبح"),
            ("13:00-14:45", "13:00", "14:45", "afternoon", "بعدازظهر"),
            ("14:46-16:30", "14:46", "16:30", "afternoon", "بعدازظهر"),
            ("16:31-18:15", "16:31", "18:15", "evening", "عصر"),
            ("18:16-20:00", "18:16", "20:00", "evening", "عصر"),
        ],
        2: [  # دو واحدی
            ("07:30-09:15", "07:30", "09:15", "morning", "صبح"),
            ("09:16-11:00", "09:16", "11:00", "morning", "صبح"),
            ("11:01-12:45", "11:01", "12:45", "morning", "صبح"),
            ("13:00-14:45", "13:00", "14:45", "afternoon", "بعدازظهر"),
            ("14:46-16:30", "14:46", "16:30", "afternoon", "بعدازظهر"),
            ("16:31-18:15", "16:31", "18:15", "evening", "عصر"),
            ("18:16-20:00", "18:16", "20:00", "evening", "عصر"),
        ],
        3: [  # سه واحدی
            ("07:30-10:10", "07:30", "10:10", "morning", "صبح"),
            ("10:11-12:50", "10:11", "12:50", "morning", "صبح"),
            ("13:00-15:30", "13:00", "15:30", "afternoon", "بعدازظهر"),
            ("15:31-18:00", "15:31", "18:00", "afternoon", "بعدازظهر"),
            ("18:01-20:30", "18:01", "20:30", "evening", "عصر"),
        ],
        4: [  # چهار واحدی
            ("07:30-10:50", "07:30", "10:50", "morning", "صبح"),
            ("12:00-16:45", "12:00", "16:45", "afternoon", "بعدازظهر"),
            ("16:46-20:30", "16:46", "20:30", "evening", "عصر"),
        ],
    },
    "semester_2": {
        1: [
            ("07:30-09:05", "07:30", "09:05", "morning", "صبح"),
            ("09:06-10:40", "09:06", "10:40", "morning", "صبح"),
            ("10:41-12:10", "10:41", "12:10", "morning", "صبح"),
            ("13:00-14:50", "13:00", "14:50", "afternoon", "بعدازظهر"),
            ("14:51-16:40", "14:51", "16:40", "afternoon", "بعدازظهر"),
            ("16:41-18:20", "16:41", "18:20", "evening", "عصر"),
            ("18:21-20:00", "18:21", "20:00", "evening", "عصر"),
        ],
        2: [
            ("07:30-09:05", "07:30", "09:05", "morning", "صبح"),
            ("09:06-10:40", "09:06", "10:40", "morning", "صبح"),
            ("10:41-12:10", "10:41", "12:10", "morning", "صبح"),
            ("13:00-14:50", "13:00", "14:50", "afternoon", "بعدازظهر"),
            ("14:51-16:40", "14:51", "16:40", "afternoon", "بعدازظهر"),
            ("16:41-18:20", "16:41", "18:20", "evening", "عصر"),
            ("18:21-20:00", "18:21", "20:00", "evening", "عصر"),
        ],
        3: [
            ("07:30-09:50", "07:30", "09:50", "morning", "صبح"),
            ("09:51-12:10", "09:51", "12:10", "morning", "صبح"),
            ("13:00-15:40", "13:00", "15:40", "afternoon", "بعدازظهر"),
            ("15:51-18:20", "15:51", "18:20", "afternoon", "بعدازظهر"),
            ("18:21-20:50", "18:21", "20:50", "evening", "عصر"),
        ],
        4: [
            ("07:30-10:40", "07:30", "10:40", "morning", "صبح"),
            ("13:00-16:20", "13:00", "16:20", "afternoon", "بعدازظهر"),
            ("16:41-20:20", "16:41", "20:20", "evening", "عصر"),
        ],
    },
    "summer": {
        # تابستان مشابه نیمسال دوم
        1: [
            ("07:30-09:05", "07:30", "09:05", "morning", "صبح"),
            ("09:06-10:40", "09:06", "10:40", "morning", "صبح"),
            ("10:41-12:10", "10:41", "12:10", "morning", "صبح"),
            ("13:00-14:50", "13:00", "14:50", "afternoon", "بعدازظهر"),
            ("14:51-16:40", "14:51", "16:40", "afternoon", "بعدازظهر"),
            ("16:41-18:20", "16:41", "18:20", "evening", "عصر"),
            ("18:21-20:00", "18:21", "20:00", "evening", "عصر"),
        ],
        2: [
            ("07:30-09:05", "07:30", "09:05", "morning", "صبح"),
            ("09:06-10:40", "09:06", "10:40", "morning", "صبح"),
            ("10:41-12:10", "10:41", "12:10", "morning", "صبح"),
            ("13:00-14:50", "13:00", "14:50", "afternoon", "بعدازظهر"),
            ("14:51-16:40", "14:51", "16:40", "afternoon", "بعدازظهر"),
            ("16:41-18:20", "16:41", "18:20", "evening", "عصر"),
            ("18:21-20:00", "18:21", "20:00", "evening", "عصر"),
        ],
        3: [
            ("07:30-09:50", "07:30", "09:50", "morning", "صبح"),
            ("09:51-12:10", "09:51", "12:10", "morning", "صبح"),
            ("13:00-15:40", "13:00", "15:40", "afternoon", "بعدازظهر"),
            ("15:51-18:20", "15:51", "18:20", "afternoon", "بعدازظهر"),
            ("18:21-20:50", "18:21", "20:50", "evening", "عصر"),
        ],
        4: [
            ("07:30-10:40", "07:30", "10:40", "morning", "صبح"),
            ("13:00-16:20", "13:00", "16:20", "afternoon", "بعدازظهر"),
            ("16:41-20:20", "16:41", "20:20", "evening", "عصر"),
        ],
    },
}


def get_slots(term="mehr", units=2, period="", start_after=None, end_before=None):
    """
    گرفتن اسلات‌های معتبر برای ترم و واحد مشخص.
    برمی‌گرداند: {"slots": [{"slot": "07:30-09:15", "start": ..., "end": ..., "period": ..., "period_title": ..., "units": n}, ...]}
    """
    term_key = normalize_term(term)
    if term_key not in SLOTS:
        return {"slots": []}
    if units not in SLOTS[term_key]:
        units = 2  # fallback
    slots = SLOTS[term_key][units]
    result = []
    for slot_str, start, end, p, p_title in slots:
        if period and p != period:
            continue
        if start_after and start < start_after:
            continue
        if end_before and end > end_before:
            continue
        result.append({
            "slot": slot_str,
            "start": start,
            "end": end,
            "period": p,
            "period_title": p_title,
            "units": units,
        })
    return {"slots": result}


def get_terms():
    """لیست ترم‌های معتبر."""
    return {
        "terms": [
            {"key": "semester_1", "title": "نیمسال اول (مهر)"},
            {"key": "semester_2", "title": "نیمسال دوم (بهمن)"},
            {"key": "summer", "title": "نیمسال تابستان"},
        ]
    }


def get_schedule(term="mehr"):
    """برنامه کامل اسلات‌های یک ترم (همه واحدها)."""
    term_key = normalize_term(term)
    if term_key not in SLOTS:
        return {"schedule": {}}
    schedule = {}
    for units, slots in SLOTS[term_key].items():
        schedule[str(units)] = [
            {"slot": s[0], "start": s[1], "end": s[2], "period": s[3], "period_title": s[4]}
            for s in slots
        ]
    return {"schedule": schedule, "term": term_key}


def is_valid_slot(start_time, end_time, term="mehr", units=2):
    """بررسی اینکه آیا جفت (start, end) با یکی از اسلات‌های استاندارد مطابقت دارد؟"""
    if not start_time or not end_time:
        return False
    data = get_slots(term=term, units=units)
    for s in data["slots"]:
        if s["start"] == start_time and s["end"] == end_time:
            return True
    return False


def get_period_for_time(start_time):
    """تعیین گروه زمانی بر اساس ساعت شروع (دقیقه).

    سه دسته (مطابق درخواست کاربر):
    - صبح (morning): 7:30 تا 12:30
    - ظهر (noon): 13:00 تا 16:00
    - بعدازظهر (afternoon): 16:00 تا 20:00
    """
    if not start_time:
        return "morning", "صبح"
    try:
        parts = start_time.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        total = hour * 60 + minute
        # صبح: 7:30 (450) تا 12:30 (750)
        if 450 <= total <= 750:
            return "morning", "صبح"
        # ظهر: 13:00 (780) تا 16:00 (960)
        elif 780 <= total < 960:
            return "noon", "ظهر"
        # بعدازظهر: 16:00 (960) تا 20:00 (1200)
        elif 960 <= total <= 1200:
            return "afternoon", "بعدازظهر"
        else:
            # خارج از بازه‌ها — پیش‌فرض صبح
            return "morning", "صبح"
    except Exception:
        return "morning", "صبح"


# ==================================================
# بازه‌های زمانی بزرگ (سه دسته)
# ==================================================

# سه دسته بازه زمانی (مطابق درخواست کاربر)
TIME_PERIODS = {
    "morning": {
        "title": "صبح",
        "title_fa": "صبح",
        "start": "07:30",
        "end": "12:30",
        "icon": "🌅",
        "description": "از ۷:۳۰ تا ۱۲:۳۰",
    },
    "noon": {
        "title": "ظهر",
        "title_fa": "ظهر",
        "start": "13:00",
        "end": "16:00",
        "icon": "☀️",
        "description": "از ۱۳:۰۰ تا ۱۶:۰۰",
    },
    "afternoon": {
        "title": "بعدازظهر",
        "title_fa": "بعدازظهر",
        "start": "16:00",
        "end": "20:00",
        "icon": "🌆",
        "description": "از ۱۶:۰۰ تا ۲۰:۰۰",
    },
}


def get_time_periods():
    """گرفتن لیست سه بازه زمانی بزرگ."""
    return {"periods": list(TIME_PERIODS.values())}
