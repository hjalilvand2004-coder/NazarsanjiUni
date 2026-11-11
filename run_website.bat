@echo off
chcp 65001 >nul
title Public Website + Admin - v3.5.0
echo ============================================
echo   Public Website + Admin Panel v3.5.0
echo   Server: http://0.0.0.0:8080
echo   Admin Login: admin / admin@1405
echo ============================================
cd /d "%~dp0"
python website.py
pause
