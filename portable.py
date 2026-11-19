# portable.py — لایهٔ مسیرهای پرتیبل/فریز (PyInstaller) برای نسخه ویندوز
# ----------------------------------------------------------------------------
# در حالت عادی (dev): مسیرها دقیقاً مثل نسخهٔ سورس می‌مانند (پروژه‌ریت/دیتا).
# در حالت فریز (PyInstaller --onedir): منابع فقط‌خواندنی از sys._MEIPASS
# و فایل‌های قابل‌نوشتن (db/json/backup) در data/ کنار فایل اجرایی قرار می‌گیرند.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))  # ریشهٔ پروژه در dev


def is_frozen() -> bool:
    """True اگر درون بستهٔ PyInstaller اجرا می‌شود."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _exe_dir() -> str:
    """شاخهٔ محل فایل اجرایی (کنار .exe در ویندوز)."""
    return os.path.dirname(os.path.abspath(sys.executable))


def res_path(*parts) -> str:
    """مسیر منابع فقط‌خواندنی (templates / static / xlsx پایه).
    dev: ریشهٔ پروژه؛ فریز: sys._MEIPASS."""
    base = sys._MEIPASS if is_frozen() else _HERE
    return os.path.join(base, *parts)


def data_path(*parts) -> str:
    """مسیر فایل‌های قابل‌نوشتن که در dev زیر data/ هستند (db / downloads / backups).
    dev: <پروژه>/data/<parts>؛ فریز: <exe>/data/<parts>."""
    if is_frozen():
        base = os.path.join(_exe_dir(), "data")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, *parts)
    return os.path.join(_HERE, "data", *parts)


def app_path(*parts) -> str:
    """مسیر فایل‌های قابل‌نوشتن که در dev در ریشهٔ پروژه هستند (json تنظیمات/پروفایل/sync).
    dev: <پروژه>/<parts>؛ فریز: <exe>/data/<parts>."""
    if is_frozen():
        base = os.path.join(_exe_dir(), "data")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, *parts)
    return os.path.join(_HERE, *parts)
