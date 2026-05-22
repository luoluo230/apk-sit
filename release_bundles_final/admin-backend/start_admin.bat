@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    set "ARGS=-Port 5003"
) else (
    set "ARGS=%*"
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0\start_admin.ps1" %ARGS%
endlocal
