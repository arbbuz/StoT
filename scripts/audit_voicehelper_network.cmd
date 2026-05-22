@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit_voicehelper_network.ps1"
echo.
pause
