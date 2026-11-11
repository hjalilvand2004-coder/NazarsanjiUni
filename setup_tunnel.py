#!/usr/bin/env python3
"""
setup_tunnel.py — راه‌اندازی تانل HTTPS برای تست مینی‌اپ بله روی لپ‌تاپ

این اسکریپت به شما کمک می‌کند یک تانل HTTPS ایجاد کنید تا بتوانید
مینی‌اپ بله را روی لپ‌تاپ خود تست کنید.

روش‌های پشتیبانی‌شده:
  1. cloudflared (توصیه‌شده — رایگان، بدون نیاز به ثبت‌نام)
  2. ngrok (نیاز به ثبت‌نام رایگان)
  3. SSH reverse tunnel (اگر سرور عمومی دارید)

استفاده:
  python setup_tunnel.py
"""

import os
import sys
import subprocess
import time
import re
import platform

def is_windows():
    return platform.system() == "Windows"

def check_cloudflared():
    """بررسی نصب بودن cloudflared"""
    try:
        result = subprocess.run(
            ["cloudflared", "version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def install_cloudflared():
    """نصب cloudflared"""
    print("📦 در حال نصب cloudflared...")
    if is_windows():
        print("   برای ویندوز: از https://github.com/cloudflare/cloudflared/releases/latest دانلود کنید")
        print("   یا با Chocolatey: choco install cloudflared")
        return False
    else:
        # لینوکس/مک
        try:
            subprocess.run(
                ["wget", "-q", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "-O", "/usr/local/bin/cloudflared"],
                check=True
            )
            subprocess.run(["chmod", "+x", "/usr/local/bin/cloudflared"], check=True)
            print("   ✓ cloudflared نصب شد")
            return True
        except subprocess.CalledProcessError as e:
            print(f"   ❌ خطا در نصب: {e}")
            return False

def start_cloudflared_tunnel(port=5000):
    """شروع تانل cloudflared"""
    print(f"\n🚀 شروع تانل HTTPS روی پورت {port}...")
    print("   (این پنجره را باز نگه دارید — Ctrl+C برای توقف)\n")

    try:
        process = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        tunnel_url = None
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
            # جستجوی URL در خروجی
            match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if match:
                tunnel_url = match.group(0)
                break

        if tunnel_url:
            print(f"\n{'='*60}")
            print(f"  ✅ تانل HTTPS فعال شد!")
            print(f"{'='*60}")
            print(f"\n  آدرس تانل: {tunnel_url}")
            print(f"\n  حالا در src/config.py این را تنظیم کنید:")
            print(f"  WEB_APP_URL = \"{tunnel_url}\"")
            print(f"\n  سپس سرویس‌ها را ری‌استارت کنید.")
            print(f"\n  یا با env variable:")
            print(f"  SERVER_HOST=<بدون پورت> و بعد از تانل URL کامل را بدهید")
            print(f"\n  برای توقف: Ctrl+C")
            print(f"{'='*60}\n")

            # منتظر بمان تا کاربر Ctrl+C بزند
            try:
                process.wait()
            except KeyboardInterrupt:
                print("\n⏹  تانل بسته شد.")
                process.terminate()
        else:
            print("❌ URL تانل پیدا نشد. خروجی بالا را بررسی کنید.")

    except FileNotFoundError:
        print("❌ cloudflared نصب نیست.")
        install_cloudflared()
    except KeyboardInterrupt:
        print("\n⏹  لغو شد.")


def main():
    print("="*60)
    print("  راه‌اندازی تانل HTTPS برای مینی‌اپ بله")
    print("="*60)
    print()
    print("⚠️  بله برای مینی‌اپ نیاز به HTTPS دارد!")
    print("   localhost و HTTP از موبایل قابل دسترس نیستند.")
    print()
    print("این اسکریپت یک تانل HTTPS رایگان ایجاد می‌کند تا بتوانید")
    print("مینی‌اپ بله را روی لپ‌تاپ خود تست کنید.")
    print()

    port = input("پورت مینی‌اپ (پیش‌فرض 5000): ").strip() or "5000"
    port = int(port)

    if not check_cloudflared():
        print("\ncloudflared نصب نیست.")
        install_choice = input("نصب شود؟ (y/n): ").strip().lower()
        if install_choice != 'y':
            print("نصب لغو شد.")
            print("\nراه‌حل دستی:")
            print("  1. cloudflared را از https://github.com/cloudflare/cloudflared/releases دانلود کنید")
            print("  2. اجرا: cloudflared tunnel --url http://127.0.0.1:5000")
            print("  3. URL https://xxx.trycloudflare.com را در src/config.py → WEB_APP_URL بگذارید")
            return
        if not install_cloudflared():
            return

    start_cloudflared_tunnel(port)


if __name__ == "__main__":
    main()
