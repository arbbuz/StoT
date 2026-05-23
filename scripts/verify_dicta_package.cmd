@echo off
setlocal
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_dicta_package.ps1" -Root "."
echo.
pause
