@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_dicta_security.ps1" -Root "."
echo.
pause
