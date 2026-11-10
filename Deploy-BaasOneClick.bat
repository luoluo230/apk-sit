@echo off
setlocal
cd /d "%~dp0"
echo Deploy-BaasOneClick ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Deploy-BaasOneClick.ps1" %*
set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo FAILED exit=%ERR%
  pause
  exit /b %ERR%
)
echo OK
pause
endlocal
