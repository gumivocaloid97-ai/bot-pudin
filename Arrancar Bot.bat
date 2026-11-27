@echo off
title Arrancar Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
runtime\python.exe inicio.py arrancar
echo.
echo   Si dice "arrancado", espera unos segundos y fijate en Discord.
echo.
timeout /t 6 >nul
