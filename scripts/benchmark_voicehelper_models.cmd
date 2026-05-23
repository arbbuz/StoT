@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0benchmark_voicehelper_models.ps1"
echo.
echo Press any key to close...
pause >nul
