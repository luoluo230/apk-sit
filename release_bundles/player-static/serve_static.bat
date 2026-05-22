@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
    set "ARGS=-Port 8080"
) else (
    set "ARGS=%*"
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0\serve_static.ps1" %ARGS%
endlocal
