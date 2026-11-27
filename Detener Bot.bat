@echo off
title Detener Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Deteniendo el bot...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = '%~dp0'.ToLower(); Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($r) } | ForEach-Object { Write-Host ('  cerrado proceso ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force }"
echo.
echo   Listo. El bot quedo apagado hasta que lo vuelvas a arrancar.
echo.
timeout /t 5 >nul
