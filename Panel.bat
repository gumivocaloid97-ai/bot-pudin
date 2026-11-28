@echo off
title Panel del Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
start "" runtime\pythonw.exe app.py
