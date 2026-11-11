@echo off
chcp 65001 >nul
title All Servers - v3.5.0
echo ============================================
echo   Starting All Services v3.5.0
echo   Mini App:    http://188.212.96.235:5000
echo   Website:     http://188.212.96.235:8080
echo   Admin Login: admin / admin@1405
echo   Bot:         Bale polling
echo ============================================
cd /d "%~dp0"
start "MiniApp v2.3" cmd /k python miniapp.py
timeout /t 2 >nul
start "Website+Admin v2.3" cmd /k python website.py
timeout /t 2 >nul
start "Bot v2.3" cmd /k python bot.py
echo All services started.
pause
