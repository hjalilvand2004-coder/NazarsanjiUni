"""
fix_bot_final.py — اصلاح نهایی بات بله
۱. اضافه‌کردن دکمه «دانلود موبایل اپ» به منوی شروع
۲. اضافه‌کردن دکمه «دانلود موبایل اپ» به پاسخ‌های کانال
۳. تنظیم دکمه دائمی منوی پایین بات
"""

import os
import sys
import re
import urllib.request
import json

INSTALL_DIR = r'C:\bale_course_survey_final'
os.chdir(INSTALL_DIR)
sys.path.insert(0, INSTALL_DIR)

# ============================================================
# ۱. اصلاح bot.py — اضافه‌کردن دکمه دانلود موبایل اپ
# ============================================================
print("=" * 60)
print("۱. اصلاح bot.py")
print("=" * 60)

bot_path = os.path.join(INSTALL_DIR, 'bot.py')
with open(bot_path, 'r', encoding='utf-8') as f:
    content = f.read()

# --- الف: اضافه‌کردن دکمه دانلود به منوی شروع ---
# پیدا کردن منوی شروع فعلی و اضافه‌کردن ردیف دکمه‌های دائمی
old_start_kb = '''        # کیبورد اینلاین با سه گزینه
        kb = [
            [{"text": "📱 مینی‌اپ بله", "callback_data": "chan_miniapp"}],
            [{"text": "🌐 وب‌سایت", "callback_data": "chan_website"}],
            [{"text": "💬 ادامه در همین بات", "callback_data": "chan_bot"}],
        ]'''

new_start_kb = '''        # کیبورد اینلاین با گزینه‌های اصلی + دکمه‌های دائمی
        kb = [
            [{"text": "📱 مینی‌اپ بله", "callback_data": "chan_miniapp"}],
            [{"text": "🌐 وب‌سایت", "callback_data": "chan_website"}],
            [{"text": "💬 ادامه در همین بات", "callback_data": "chan_bot"}],
            [
                {"text": "🌐 باز کردن سایت", "url": WEBSITE_URL},
                {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
            ],
        ]'''

if old_start_kb in content:
    content = content.replace(old_start_kb, new_start_kb)
    print("  ✓ دکمه دانلود به منوی شروع اضافه شد")
else:
    # الگوهای دیگر را امتحان کن
    pattern = r'(\[?\{"text": "💬 ادامه در همین بات", "callback_data": "chan_bot"\}?\],?\s*)\n\s*\]'
    replacement = r'''\1,
            [
                {"text": "🌐 باز کردن سایت", "url": WEBSITE_URL},
                {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
            ],
        ]'''
    new_content = re.sub(pattern, replacement, content)
    if new_content != content:
        content = new_content
        print("  ✓ دکمه دانلود به منوی شروع اضافه شد (الگو ۲)")
    else:
        print("  ⚠ منوی شروع پیدا نشد — شاید قبلاً اضافه شده")

# --- ب: اضافه‌کردن دکمه دانلود به پاسخ مینی‌اپ ---
old_miniapp_response = '''        if choice == "chan_miniapp":
            msg = MESSAGES["channel_chosen_miniapp"].format(web_app_url=WEB_APP_URL)
            # دکمه اینلاین برای باز کردن مینی‌اپ
            kb = self.api.create_inline_keyboard([
                [{"text": "🌐 ورود به مینی‌اپ", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])'''

new_miniapp_response = '''        if choice == "chan_miniapp":
            msg = MESSAGES["channel_chosen_miniapp"].format(web_app_url=WEB_APP_URL)
            # دکمه‌های اینلاین: مینی‌اپ + وب‌سایت + دانلود موبایل اپ + بازگشت
            kb = self.api.create_inline_keyboard([
                [{"text": "🌐 ورود به مینی‌اپ", "web_app": {"url": WEB_APP_URL}}],
                [
                    {"text": "🌐 وب‌سایت", "url": WEBSITE_URL},
                    {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
                ],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])'''

if old_miniapp_response in content:
    content = content.replace(old_miniapp_response, new_miniapp_response)
    print("  ✓ دکمه دانلود به پاسخ مینی‌اپ اضافه شد")
else:
    print("  ⚠ پاسخ مینی‌اپ پیدا نشد — شاید قبلاً اضافه شده")

# --- ج: اضافه‌کردن دکمه دانلود به پاسخ وب‌سایت ---
old_website_response = '''        elif choice == "chan_website":
            msg = MESSAGES["channel_chosen_website"].format(website_url=WEBSITE_URL)
            kb = self.api.create_inline_keyboard([
                [{"text": "🌐 باز کردن وب‌سایت", "url": WEBSITE_URL}],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])'''

new_website_response = '''        elif choice == "chan_website":
            msg = MESSAGES["channel_chosen_website"].format(website_url=WEBSITE_URL)
            kb = self.api.create_inline_keyboard([
                [
                    {"text": "🌐 باز کردن وب‌سایت", "url": WEBSITE_URL},
                    {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
                ],
                [{"text": "📱 ورود به مینی‌اپ", "web_app": {"url": WEB_APP_URL}}],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])'''

if old_website_response in content:
    content = content.replace(old_website_response, new_website_response)
    print("  ✓ دکمه دانلود به پاسخ وب‌سایت اضافه شد")
else:
    print("  ⚠ پاسخ وب‌سایت پیدا نشد — شاید قبلاً اضافه شده")

# ذخیره فایل
with open(bot_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("  ✓ bot.py ذخیره شد")


# ============================================================
# ۲. تنظیم دکمه دائمی منوی پایین بات
# ============================================================
print()
print("=" * 60)
print("۲. تنظیم دکمه دائمی منوی پایین بات")
print("=" * 60)

try:
    from src.config import BALE_BOT_TOKEN, WEB_APP_URL, WEBSITE_URL
    print(f"  Bot Token: {BALE_BOT_TOKEN[:20]}...")
    print(f"  Web App URL: {WEB_APP_URL}")
    print(f"  Website URL: {WEBSITE_URL}")

    # تلاش با فرمت‌های مختلف API بله
    api_urls = [
        f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/setChatMenuButton",
        f"https://tapi.bale.ai/bot{BALE_BOT_TOKEN}/setMenuButton",
    ]

    data = json.dumps({
        "menu_button": {
            "type": "web_app",
            "text": "📱 ورود به مینی‌اپ",
            "web_app": {"url": WEB_APP_URL}
        }
    }).encode()

    success = False
    for api_url in api_urls:
        try:
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    print(f"  ✓ دکمه منوی پایین تنظیم شد: {api_url}")
                    success = True
                    break
                else:
                    print(f"  ⚠ پاسخ API: {result}")
        except urllib.error.HTTPError as e:
            print(f"  ⚠ {api_url} → HTTP {e.code}")
        except Exception as e:
            print(f"  ⚠ {api_url} → {e}")

    if not success:
        print("  ℹ دکمه دائمی منو تنظیم نشد — اما دکمه‌های اینلاین در پیام‌ها کار می‌کنند")

except Exception as e:
    print(f"  ⚠ خطا: {e}")


# ============================================================
# ۳. خلاصه
# ============================================================
print()
print("=" * 60)
print("  ✅ اصلاحات انجام شد!")
print("=" * 60)
print()
print("  تغییرات اعمال‌شده:")
print("    ۱. دکمه «📲 دانلود موبایل اپ» به منوی شروع اضافه شد")
print("    ۲. دکمه دانلود به پاسخ‌های مینی‌اپ و وب‌سایت اضافه شد")
print("    ۳. تلاش برای تنظیم دکمه دائمی منوی پایین")
print()
print("  حالا سرویس بات را ری‌استارت کنید:")
print("    Restart-Service SurveyBot -Force")
print()
print("  سپس در بله /start را بزنید.")
print()
