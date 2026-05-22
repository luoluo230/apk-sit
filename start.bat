@echo off
title APK Site Dual Portal Launcher
cd /d "%~dp0"
set "START_MODE=%~1"
set "PS_ARGS=-NoProfile -ExecutionPolicy Bypass -File ""%~dp0scripts\start_dual_portals.ps1"""
if /I "%START_MODE%"=="scheduled" set "PS_ARGS=%PS_ARGS% -UseScheduledTasks"
powershell %PS_ARGS%
start "Admin Portal Log" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Admin portal log: %~dp0logs\admin-portal.log'; if (!(Test-Path '%~dp0logs\admin-portal.log')) { New-Item -ItemType File -Path '%~dp0logs\admin-portal.log' | Out-Null }; Get-Content '%~dp0logs\admin-portal.log' -Wait"
start "Player Portal Log" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command "Write-Host 'Player portal log: %~dp0logs\player-portal.log'; if (!(Test-Path '%~dp0logs\player-portal.log')) { New-Item -ItemType File -Path '%~dp0logs\player-portal.log' | Out-Null }; Get-Content '%~dp0logs\player-portal.log' -Wait"
