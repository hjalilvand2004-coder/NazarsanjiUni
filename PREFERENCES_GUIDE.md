# راهنمای مطلوبیت‌های تدریس و زمان‌بندی اساتید — نسخه 3.8.0

## فایل‌های اضافه/اصلاح‌شده

| فایل | وضعیت | توضیح |
|------|------|------|
| `slot_times.py` | **جدید** | منبع مرجع اسلات‌های استاندارد + DAY_MAP + normalize_day/term |
| `preferences.py` | **جدید** | ماژول کامل مطلوبیت‌ها — مدل، CRUD، آپلود اکسل، load برای موتور |
| `website.py` | اصلاح | افزودن ۱۱ مسیر API + صفحه admin/preferences |
| `templates/admin/preferences.html` | **جدید** | صفحه مدیریت با تب‌ها، مودال‌ها، آپلود اکسل |
| `templates/admin/base.html` | اصلاح | لینک «مطلوبیت‌های اساتید» در سایدبار |
| `PREFERENCES_GUIDE.md` | **جدید** | این فایل |

## نکات حیاتی

### ✅ دیتابیس و دیتای فعلی کاملاً امن است
- **هیچ تغییری در جداول موجود داده نشد.**
- جداول جدید `teaching_preferences` و `time_preferences` با `CREATE TABLE IF NOT EXISTS` ساخته می‌شوند.
- migration کاملاً additive و idempotent است.
- تست شده: 31 کاربر، 143 درس، 95 درس یکتا، 87 درخواست، 1 نظرسنجی — همه دست‌نخورده باقی ماندند.

### ✅ تنظیمات سرور و اتصال تغییر نکرد
- `src/config.py` — بدون تغییر
- پورت‌ها، IPها، توکن‌ها — همه دست‌نخورده
- SSO و همه قابلیت‌های قبلی حفظ شده‌اند

## مسیرهای API (مطابق پرامپت)

### Slot Times (منبع مرجع)
| متد | مسیر | توضیح |
|-----|------|------|
| GET | `/api/slot-times/search?term=&units=&period=` | اسلات‌های معتبر |
| GET | `/api/slot-times/terms` | لیست ترم‌ها |
| GET | `/api/slot-times/schedule?term=` | برنامه کامل یک ترم |

### Teaching Preferences
| متد | مسیر | توضیح |
|-----|------|------|
| GET | `/api/teaching-preferences` | لیست |
| POST | `/api/teaching-preferences` | ساخت (با normalize_code) |
| PUT | `/api/teaching-preferences/{id}` | ویرایش |
| DELETE | `/api/teaching-preferences/{id}` | حذف |
| POST | `/api/teaching-preferences/upload` | آپلود اکسل |

### Time Preferences
| متد | مسیر | توضیح |
|-----|------|------|
| GET | `/api/time-preferences` | لیست |
| POST | `/api/time-preferences` | ساخت |
| POST | `/api/time-preferences/bulk` | ساخت گروهی (برای TimeSlotSelector) |
| PUT | `/api/time-preferences/{id}` | ویرایش |
| DELETE | `/api/time-preferences/{id}` | حذف |
| POST | `/api/time-preferences/upload?term=mehr` | آپلود اکسل با اعتبارسنجی اسلات |

### صفحه ادمین
- `/admin/preferences` — صفحه مدیریت با تب‌ها و مودال‌ها

## ساختار جداول

### teaching_preferences
```sql
CREATE TABLE teaching_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_course_code TEXT,
    course_name TEXT,
    cooperation_type TEXT,
    expert_group TEXT,
    row_number INTEGER,
    instructor_code TEXT,
    instructor_name TEXT,
    instructor_username TEXT,
    status TEXT DEFAULT 'pending',  -- pending, approved, rejected
    term_code TEXT,
    priority INTEGER DEFAULT 999,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### time_preferences
```sql
CREATE TABLE time_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT,
    cooperation_type TEXT,
    end_time TEXT,
    expert_group TEXT,
    row_number INTEGER,
    status INTEGER DEFAULT 1,  -- Boolean
    instructor_code TEXT,
    instructor_name TEXT,
    instructor_username TEXT,
    start_time TEXT,
    time_group TEXT,  -- morning, afternoon, evening
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## نقشه ستون‌های اکسل

### مطلوبیت تدریس (teaching_preferences)
| ستون اکسل (فارسی) | فیلد مدل |
|---|---|
| `کد یکتا درس` | unique_course_code |
| `نام درس` | course_name |
| `نوع همکاری` | cooperation_type |
| `گروه تخصصی` | expert_group |
| `ردیف` | row_number |
| `کد استاد` | instructor_code |
| `نام استاد` | instructor_name |
| `یوزرنیم استاد` | instructor_username |
| `وضعیت` | status |
| `کد ترم تحصیلی` | term_code |

### مطلوبیت زمان (time_preferences)
| ستون اکسل (فارسی) | فیلد مدل |
|---|---|
| `روز` | day |
| `نوع همکاری` | cooperation_type |
| `زمان پایان` | end_time |
| `گروه تخصصی` | expert_group |
| `ردیف` | row_number |
| `وضعیت` | status (تبدیل به Boolean) |
| `کد استاد` | instructor_code |
| `استاد` | instructor_name |
| `یوزرنیم استاد` | instructor_username |
| `زمان شروع` | start_time |
| `گروه زمانی` | time_group |
| `اولویت` | priority |

## اسلات‌های استاندارد (نیمسال اول، ۲ واحدی)

| شروع | پایان | گروه |
|------|------|------|
| 07:30 | 09:15 | صبح |
| 09:16 | 11:00 | صبح |
| 11:01 | 12:45 | صبح |
| 13:00 | 14:45 | بعدازظهر |
| 14:46 | 16:30 | بعدازظهر |
| 16:31 | 18:15 | عصر |
| 18:16 | 20:00 | عصر |

> برای ۳ و ۴ واحدی و نیمسال دوم/تابستان به `slot_times.py` مراجعه کنید.

## گزارش تطابق

تابع `get_match_status(item, teaching_lookup, time_lookup)` چهار وضعیت برمی‌گرداند:

| وضعیت | معنی | نمایش |
|-------|------|------|
| `full` | تطابق کامل (استاد + روز + زمان) | ✅ تطابق کامل |
| `partial` | تطابق نسبی (۱ یا ۲ از ۳) | ⚠️ تطابق نسبی |
| `none` | بدون تطابق | ❌ بدون تطابق |
| `no_preference` | هیچ مطلوبیتی ثبت نشده | ➖ بدون مطلوبیت |

رواداری زمان: ±۶۰ دقیقه (تابع `is_time_slot_match_withTolerance`)

## راه‌اندازی

### ۱. نصب وابستگی‌ها
```bash
pip install pandas openpyxl
```
(احتمالاً قبلاً نصب هستند چون وب‌سایت فعلی از اکسل استفاده می‌کند)

### ۲. بکاپ بگیرید
```powershell
# بکاپ دیتابیس (الزامی!)
Copy-Item data\courses_survey.db data\courses_survey.db.bak-before-prefs

# بکاپ فایل‌ها
Copy-Item website.py website.py.bak-before-prefs
Copy-Item templates\admin\base.html templates\admin\base.html.bak-before-prefs
```

### ۳. جایگزینی فایل‌ها
- `slot_times.py` (جدید — در ریشه پروژه)
- `preferences.py` (جدید — در ریشه پروژه)
- `website.py` (اصلاح‌شده)
- `templates/admin/preferences.html` (جدید)
- `templates/admin/base.html` (اصلاح‌شده)

### ۴. ری‌استارت وب‌سایت
```powershell
.\Restart-Website.ps1
```

### ۵. تست
1. وارد پنل ادمین شوید
2. سایدبار: **سیستم → مطلوبیت‌های اساتید**
3. باید صفحه با دو تب «مطلوبیت‌های تدریس» و «مطلوبیت‌های زمان» نمایش داده شود
4. دکمه «افزودن» و «بارگذاری اکسل» را تست کنید
5. API: `GET /api/slot-times/search?term=mehr&units=2` را در مرورگر باز کنید

## ادغام با موتور زمان‌بندی (آماده استفاده)

تابع `load_instructor_preferences_for_scheduler(db)` در `preferences.py` آماده استفاده است:

```python
from preferences import load_instructor_preferences_for_scheduler

teaching_prefs, time_prefs = load_instructor_preferences_for_scheduler(db)
# teaching_prefs: dict[course_code] = [inst_code, ...]  (مرتب بر اساس اولویت)
# time_prefs: dict[inst_code] = [(day_num, start, end, priority), ...]
```

این تابع مطابق مشخصات پرامپت:
- اولویت‌بندی بر اساس `(priority صعودی, اولویت همکاری نزولی)`
- نرمال‌سازی نام روز با `normalize_day` + `DAY_MAP`
- لاگ هشدار برای روزهای ناشناخته
- لاگ پایانی با تعداد
