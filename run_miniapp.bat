@echo off
chcp 65001 >nul
title Mini App Server - v3.5.0
echo ============================================
echo   Mini App v3.5.0
echo   Server: http://0.0.0.0:5000
echo ============================================
cd /d "%~dp0"
python miniapp.py
pause
