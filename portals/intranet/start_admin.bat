@echo off
set "ROOT_DIR=%~dp0..\.."
cd /d "%ROOT_DIR%"
if "%APK_PORT%"=="" set "APK_PORT=5003"
set "JENKINS_WAR_PATH=%ROOT_DIR%\portals\common\core\jenkins-clone\jenkins.war"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\portals\common\core\scripts\run_portal_waitress.ps1" -Mode admin -AppPort %APK_PORT%
