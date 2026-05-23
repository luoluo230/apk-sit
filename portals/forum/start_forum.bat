@echo off
set "ROOT_DIR=%~dp0..\.."
cd /d "%ROOT_DIR%"
if "%APK_PORT%"=="" set "APK_PORT=5005"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\portals\common\core\scripts\run_portal_waitress.ps1" -Mode forum -AppPort %APK_PORT%
