@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_russian_spellcheck.ps1"
echo.
pause
