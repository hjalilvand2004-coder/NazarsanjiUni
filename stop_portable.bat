@echo off
chcp 65001 >nul
echo در حال توقف BaleSurvey...
taskkill /F /IM BaleSurvey.exe >nul 2>&1
if %ERRORLEVEL%==0 (
    echo ✅ سرور متوقف شد.
) else (
    echo ⚠️ پردازش BaleSurvey یافت نشد (احتمالاً از قبل بسته است).
)
timeout /t 2 >nul
