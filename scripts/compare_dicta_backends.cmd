@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0compare_dicta_backends.ps1"
echo.
echo Press any key to close...
pause >nul
