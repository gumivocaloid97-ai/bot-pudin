@echo off
title Registro del bot
chcp 65001 >nul
cd /d "%~dp0"
if not exist bot.log goto sin
start "" notepad "%~dp0bot.log"
exit /b 0
:sin
echo.
echo   Todavia no hay bot.log. El bot no arranco nunca desde esta carpeta.
echo.
pause >nul
