#!/usr/bin/env python3
"""
build_apk.py — ساخت APK موبایل اپ دانشجو۳۶۰ با URL دلخواه

پشتیبانی کامل از اندروید 10 (API 29) به بعد

استفاده:
    python build_apk.py [URL] [VERSION]

مثال:
    python build_apk.py http://127.0.0.1:8080/app 1.0.0
    python build_apk.py http://188.212.96.235:8080/app 1.0.1
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# تنظیمات
SCRIPT_DIR = Path(__file__).parent.resolve()
APP_DIR = SCRIPT_DIR / "app-source"
BUILD_DIR = SCRIPT_DIR / "build_apk_output"
OUTPUT_NAME = "daneshjoo360-v{version}.apk"

# مسیر SDK و JDK (قابل override با env)
ANDROID_HOME = os.environ.get("ANDROID_HOME", "/home/z/android-sdk")
JAVA_HOME = os.environ.get("JAVA_HOME", "/home/z/jdk17")
BUILD_TOOLS = os.environ.get("ANDROID_BUILD_TOOLS", "34.0.0")

def run(cmd, check=True):
    """اجرای دستور با نمایش"""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[-1000:])
    if result.returncode != 0 and check:
        print(f"  ❌ Error: {result.stderr[-1000:]}")
        sys.exit(1)
    return result

def build_apk(target_url: str, version: str = "1.0.0") -> Path:
    """ساخت APK با URL مشخص"""
    print(f"\n🏗  ساخت APK دانشجو۳۶۰ v{version}")
    print(f"   URL: {target_url}")
    print(f"   Android SDK: {ANDROID_HOME}")
    print(f"   JDK: {JAVA_HOME}")
    print(f"   Min SDK: 29 (Android 10)")
    print(f"   Target SDK: 34 (Android 14)")

    # مسیرهای ابزار
    aapt2 = f"{ANDROID_HOME}/build-tools/{BUILD_TOOLS}/aapt2"
    d8 = f"{ANDROID_HOME}/build-tools/{BUILD_TOOLS}/d8"
    zipalign = f"{ANDROID_HOME}/build-tools/{BUILD_TOOLS}/zipalign"
    apksigner = f"{ANDROID_HOME}/build-tools/{BUILD_TOOLS}/apksigner"
    javac = f"{JAVA_HOME}/bin/javac"
    keytool = f"{JAVA_HOME}/bin/keytool"
    android_jar = f"{ANDROID_HOME}/platforms/android-34/android.jar"

    # پاکسازی
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)
    (BUILD_DIR / "obj").mkdir()
    (BUILD_DIR / "compiled_resources").mkdir()
    (BUILD_DIR / "dex").mkdir()

    # مرحله ۱: جایگزینی URL در MainActivity.java (hardcode)
    print("\n[1/8] جایگزینی URL در کد...")
    java_src = APP_DIR / "src/main/java/com/daneshjoo360/app/MainActivity.java"
    content = java_src.read_text(encoding="utf-8")
    import re
    # جایگزینی خط: String url = "..."
    content = re.sub(
        r'String url = "[^"]+";',
        f'String url = "{target_url}";',
        content
    )
    java_src.write_text(content, encoding="utf-8")
    print(f"   ✓ URL تنظیم شد: {target_url}")

    # مرحله ۲: کامپایل منابع
    print("\n[2/8] کامپایل منابع (aapt2 compile)...")
    run(f"{aapt2} compile --dir {APP_DIR}/src/main/res -o {BUILD_DIR}/compiled_resources/")

    # مرحله ۳: لینک منابع
    print("\n[3/8] لینک منابع (aapt2 link)...")
    run(f"{aapt2} link -I {android_jar} --manifest {APP_DIR}/src/main/AndroidManifest.xml "
        f"-o {BUILD_DIR}/app-unsigned.apk --java {BUILD_DIR}/obj "
        f"-R {BUILD_DIR}/compiled_resources/*.flat --auto-add-overlay "
        f"--min-sdk-version 29 --target-sdk-version 34")

    # مرحله ۴: کامپایل Java
    print("\n[4/8] کامپایل Java (javac)...")
    # پیدا کردن همه فایل‌های Java
    java_files = list((APP_DIR / "src/main/java").rglob("*.java"))
    java_files_str = " ".join(str(f) for f in java_files)
    run(f"{javac} -source 17 -target 17 -classpath {android_jar} "
        f"-d {BUILD_DIR}/obj {java_files_str}")

    # مرحله ۵: تبدیل به DEX
    print("\n[5/8] تبدیل به DEX (d8)...")
    # استفاده از shell glob به جای Python glob (برای جلوگیری از مشکل کاراکترهای $)
    run(f"cd {BUILD_DIR} && {d8} --release --min-api 29 --lib {android_jar} --output dex obj/com/daneshjoo360/app/*.class")

    # مرحله ۶: اضافه‌کردن DEX به APK
    print("\n[6/8] اضافه‌کردن DEX به APK...")
    run(f"cd {BUILD_DIR} && zip -j app-unsigned.apk dex/classes.dex")

    # مرحله ۷: align
    print("\n[7/8] Align APK (zipalign)...")
    run(f"{zipalign} -v -p 4 {BUILD_DIR}/app-unsigned.apk {BUILD_DIR}/app-aligned.apk")

    # مرحله ۸: ساخت keystore و امضای APK
    print("\n[8/8] امضای APK (apksigner)...")
    run(f"{keytool} -genkeypair -keystore {BUILD_DIR}/debug.keystore "
        f"-storepass android -alias androiddebugkey -keypass android "
        f"-keyalg RSA -keysize 2048 -validity 10000 "
        f'-dname "CN=Daneshjoo360, OU=App, O=University, L=Tehran, ST=Tehran, C=IR"')

    output_apk = BUILD_DIR / OUTPUT_NAME.format(version=version)
    run(f"{apksigner} sign --ks {BUILD_DIR}/debug.keystore "
        f"--ks-pass pass:android --ks-key-alias androiddebugkey "
        f"--key-pass pass:android --out {output_apk} {BUILD_DIR}/app-aligned.apk")

    # تأیید امضا
    run(f"{apksigner} verify --verbose {output_apk}")

    print(f"\n✅ APK ساخته شد!")
    print(f"   فایل: {output_apk}")
    print(f"   حجم: {output_apk.stat().st_size // 1024} کیلوبایت")
    print(f"   Min SDK: 29 (Android 10)")
    print(f"   Target SDK: 34 (Android 14)")
    return output_apk


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/app"
    version = sys.argv[2] if len(sys.argv) > 2 else "1.0.0"
    build_apk(url, version)
