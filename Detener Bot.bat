@echo off
title Detener Bot Pudin
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo   Deteniendo el bot...
echo.
echo apagado a pedido> "%~dp0detener.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = '%~dp0'.ToLower(); Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and (($_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($r)) -or ($_.CommandLine -and $_.CommandLine.ToLower().Contains($r))) } | ForEach-Object { Write-Host ('  cerrado proceso ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo   Listo. Queda apagado hasta que lo prendas con Pudin.bat.
echo.
timeout /t 5 >nul
