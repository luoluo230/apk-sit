@echo off
cd /d "%~dp0"
if "%APK_PORT%"=="" set "APK_PORT=5005"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_portal_waitress.ps1" -Mode forum -AppPort %APK_PORT%
