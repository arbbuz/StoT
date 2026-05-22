@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_voicehelper.ps1" -Root "."
echo.
pause
