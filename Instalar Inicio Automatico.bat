@echo off
title Inicio automatico
chcp 65001 >nul
cd /d "%~dp0"
echo.
runtime\python.exe inicio.py instalar
echo.
echo   Presiona una tecla para cerrar.
pause >nul
