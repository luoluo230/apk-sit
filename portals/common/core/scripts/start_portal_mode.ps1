param(
    [string]$AppDir = "",
    [ValidateSet('admin', 'player', 'forum')]
    [string]$Mode = 'admin',
    [int]$Port = 0,
    [switch]$ShowLogWindow
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($AppDir)) {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $AppDir = Split-Path -Parent $PSScriptRoot
    } elseif ($MyInvocation.MyCommand.Path) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $AppDir = Split-Path -Parent $scriptDir
    } else {
        throw "Unable to resolve AppDir from script context."
    }
}
$AppDir = (Resolve-Path $AppDir).Path
Set-Location $AppDir

if ($Port -le 0) {
    if ($Mode -eq 'admin') { $Port = 5003 }
    elseif ($Mode -eq 'player') { $Port = 5004 }
    else { $Port = 5005 }
}

$runner = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
$args = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', $runner,
    '-AppDir', $AppDir,
    '-Mode', $Mode,
    '-AppPort', $Port
)

$proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $args -WorkingDirectory $AppDir -WindowStyle Hidden -PassThru

$logDir = Join-Path $AppDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "$Mode-portal.log"

if ($ShowLogWindow) {
    $displayText = "$($Mode) portal log: $($logPath)"
    $command = "Write-Host '$displayText'; if (!(Test-Path '$logPath')) { New-Item -ItemType File -Path '$logPath' | Out-Null }; Get-Content '$logPath' -Wait"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', $command
    ) -WindowStyle Normal | Out-Null
}

Write-Output "Mode: $Mode"
Write-Output "Port: $Port"
Write-Output "URL:  http://127.0.0.1:$Port"
Write-Output "PID:  $($proc.Id)"
Write-Output "Log:  $logPath"
