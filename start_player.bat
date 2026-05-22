@echo off
cd /d "%~dp0"
if "%APK_PORT%"=="" set "APK_PORT=5004"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_portal_waitress.ps1" -Mode player -AppPort %APK_PORT%
