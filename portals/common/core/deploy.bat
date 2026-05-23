@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

title APK Download Center - Windows
echo ================================================
echo   APK Download Center - Windows Launcher
echo ================================================
echo.

set "PYTHON_CMD="
python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD py --version >nul 2>&1 && set "PYTHON_CMD=py"
if not defined PYTHON_CMD if exist "C:\python\python.exe" set "PYTHON_CMD=C:\python\python.exe"
if not defined PYTHON_CMD if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYTHON_CMD if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python310\python.exe"
if not defined PYTHON_CMD if exist "%LocalAppData%\Programs\Python\Python39\python.exe" set "PYTHON_CMD=%LocalAppData%\Programs\Python\Python39\python.exe"

if not defined PYTHON_CMD (
    echo [ERROR] Python 3.8+ not found.
    echo Install Python or add it to PATH. This script also checks C:\python\python.exe.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('"%PYTHON_CMD%" --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [OK] Python version: %PYTHON_VERSION%

"%PYTHON_CMD%" -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Flask not found. Installing...
    "%PYTHON_CMD%" -m pip install flask -q
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Flask.
        pause
        exit /b 1
    )
    echo [OK] Flask installed.
) else (
    echo [OK] Flask already installed.
)

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [OK] Created .env from .env.example
    )
)

if not exist "logs" mkdir logs

:MENU
echo.
echo Choose an action:
echo   1) Start in foreground
echo   2) Start in background
echo   3) Stop service
echo   4) Restart service
echo   5) Configure autostart
echo   6) View logs
echo   0) Exit
echo.

set /p choice="Select [0-6]: "

if "%choice%"=="1" goto START
if "%choice%"=="2" goto START_BG
if "%choice%"=="3" goto STOP
if "%choice%"=="4" goto RESTART
if "%choice%"=="5" goto AUTOSTART
if "%choice%"=="6" goto LOGS
if "%choice%"=="0" exit /b
goto MENU

:START
echo [START] Running app in foreground...
"%PYTHON_CMD%" app_new.py
goto MENU

:START_BG
echo [START] Running app in background...
start /b "" "%PYTHON_CMD%" app_new.py
echo [OK] Service started.
goto MENU

:STOP
echo [STOP] Stopping python processes started for this app...
taskkill /F /FI "IMAGENAME eq python.exe" >nul 2>&1
taskkill /F /FI "IMAGENAME eq py.exe" >nul 2>&1
echo [OK] Stop command sent.
goto MENU

:RESTART
echo [RESTART] Restarting service...
taskkill /F /FI "IMAGENAME eq python.exe" >nul 2>&1
taskkill /F /FI "IMAGENAME eq py.exe" >nul 2>&1
timeout /t 2 /nobreak >nul
start /b "" "%PYTHON_CMD%" app_new.py
echo [OK] Service restarted.
goto MENU

:AUTOSTART
echo [SETUP] Creating startup shortcut script...
(
    echo @echo off
    echo cd /d "%SCRIPT_DIR%"
    echo "%PYTHON_CMD%" app_new.py
) > start_apk_site.bat
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
copy /Y start_apk_site.bat "%STARTUP_DIR%\" >nul
echo [OK] Autostart configured.
goto MENU

:LOGS
echo [LOGS] Showing log files under logs\
if exist "logs\*.log" (
    type logs\*.log | more
) else (
    echo [INFO] No log files found.
)
goto MENU
