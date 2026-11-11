# 🔧 راهنمای باز کردن مینی‌اپ در بات بله

## ❓ چرا مینی‌اپ باز نمی‌شود؟

مینی‌اپ بله **نیاز به HTTPS** دارد. وقتی روی لپ‌تاپ با `http://127.0.0.1:5000` کار می‌کنید، بله نمی‌تواند آن را باز کند چون:

۱. بله فقط **HTTPS** قبول می‌کند (نه HTTP)
۲. `127.0.0.1` و `localhost` از موبایل کاربر قابل دسترس نیستند
۳. باید آدرس عمومی با HTTPS داشته باشید

## ✅ راه‌حل‌ها

### روش ۱: استفاده از تانل (سریع‌ترین برای تست)

```bash
# اسکریپت خودکار
python setup_tunnel.py

# یا دستی با cloudflared:
cloudflared tunnel --url http://127.0.0.1:5000
```

یک URL مثل این دریافت می‌کنید:
```
https://abc-def-ghi.trycloudflare.com
```

سپس در `src/config.py`:
```python
WEB_APP_URL = "https://abc-def-ghi.trycloudflare.com"
```

سرویس‌ها را ری‌استارت کنید. حالا مینی‌اپ از بات بله باز می‌شود!

### روش ۲: ngrok

```bash
# نصب از ngrok.com
ngrok http 5000

# URL مثل: https://xxxx.ngrok.io
# در src/config.py:
WEB_APP_URL = "https://xxxx.ngrok.io"
```

### روش ۳: سرور با HTTPS (پروداکشن)

اگر سرور با دامنه و SSL دارید:
```bash
SERVER_HOST=your-domain.com python website.py
```

### روش ۴: تست بدون بله (مستقیم در مرورگر)

برای تست بدون نیاز به تانل:
```
http://127.0.0.1:5000
```

این در مرورگر لپ‌تاپ کار می‌کند، فقط داخل بله باز نمی‌شود.

## 📋 مراحل کامل تست مینی‌اپ در بله

۱. مینی‌اپ را اجرا کنید:
```bash
python miniapp.py
# خروجی: Server: http://0.0.0.0:5000
```

۲. در terminal دیگر، تانل HTTPS راه‌اندازی کنید:
```bash
python setup_tunnel.py
# یا:
cloudflared tunnel --url http://127.0.0.1:5000
```

۳. URL تانل را در `src/config.py` بگذارید:
```python
WEB_APP_URL = "https://xxx-yyy.trycloudflare.com"
```

۴. بات را اجرا کنید:
```bash
python bot.py
```

۵. در بله، به بات خود `/start` بزنید → «📱 مینی‌اپ بله» را انتخاب کنید

۶. روی دکمه «🌐 ورود به مینی‌اپ» بزنید — حالا باید باز شود!

## ⚠️ نکات مهم

- **تانل cloudflared رایگان است** ولی هر بار که ری‌استارت می‌شود URL تغییر می‌کند
- برای URL ثابت، باید cloudflare account داشته باشید (باز هم رایگان)
- **هر بار که URL تغییر کرد**، باید `WEB_APP_URL` را به‌روز کنید و بات را ری‌استارت کنید
- در `BotFather` بله هم می‌توانید با `/setmenubutton` دکمه منو را تنظیم کنید
