@echo off
title Diagnostico del Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo Falta la carpeta runtime.
  pause
  exit /b 1
)
runtime\python.exe diagnostico.py
