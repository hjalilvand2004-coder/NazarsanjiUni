@echo off
chcp 65001 >nul
title Bale Bot - v3.5.0
echo ============================================
echo   Bale Bot v3.5.0
echo ============================================
cd /d "%~dp0"
python bot.py
pause
