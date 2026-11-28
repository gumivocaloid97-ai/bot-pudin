@echo off
title Panel del Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Abriendo el panel del bot...
echo.
runtime\pythonw.exe -c "import bandeja; bandeja._abrir_panel()"
timeout /t 2 >nul
