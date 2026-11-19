@echo off
chcp 65001 >nul
title سامانه نظرسنجی دروس - Portable
cd /d "%~dp0"
set BALE_HOST=127.0.0.1
set BALE_PORT=8082
echo ============================================
echo   سامانه نظرسنجی دروس - نسخه پرتیبل ویندوز
echo   آدرس:   http://127.0.0.1:8082
echo   ادمین:  admin / admin@1405
echo   برای توقف: Ctrl+C  (یا فایل stop_portable.bat)
echo ============================================
echo.
echo در حال اجرای سرور... مرورگر پس از چند ثانیه باز می‌شود.
start "" /min cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:8082"
BaleSurvey.exe
echo.
echo سرور متوقف شد.
pause
