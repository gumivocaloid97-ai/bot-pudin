@echo off
title Quitar inicio automatico
chcp 65001 >nul
cd /d "%~dp0"
echo.
runtime\python.exe inicio.py quitar
echo.
echo   Presiona una tecla para cerrar.
pause >nul
