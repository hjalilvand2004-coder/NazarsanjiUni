@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Build BaleSurvey Portable (Windows)
echo ============================================
echo.
echo [1/4] Checking Python...
python --version || (echo ❌ Python not found on PATH & pause & exit /b 1)
echo.
echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
echo.
echo [3/4] Building with PyInstaller (onedir)...
python -m PyInstaller BaleSurvey.spec --noconfirm --clean
if %ERRORLEVEL% neq 0 (echo ❌ Build failed. & pause & exit /b 1)
echo.
echo [4/4] Assembling portable folder...
copy /Y run_portable.bat dist\BaleSurvey\ >nul
copy /Y stop_portable.bat dist\BaleSurvey\ >nul
copy /Y README_PORTABLE_WINDOWS.md dist\BaleSurvey\ >nul
echo.
echo ✅ Done. Portable folder:  dist\BaleSurvey\
echo    Run:  dist\BaleSurvey\run_portable.bat
echo.
pause
