@echo off
title Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\pythonw.exe" (
  echo.
  echo   Falta la carpeta "runtime" al lado de este archivo.
  echo   Volve a descomprimir BotPudin-portable.zip completo.
  echo.
  pause
  exit /b 1
)
start "" runtime\pythonw.exe pudin.py
