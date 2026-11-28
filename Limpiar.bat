@echo off
title Limpiar Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo Falta la carpeta runtime.
  pause
  exit /b 1
)
runtime\python.exe limpiar.py
timeout /t 3 >nul
start "" runtime\pythonw.exe pudin.py
timeout /t 2 >nul
