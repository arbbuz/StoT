@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_voicehelper_security.ps1" -Root "."
echo.
pause
