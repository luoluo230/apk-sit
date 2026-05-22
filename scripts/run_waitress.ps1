param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [ValidateSet('admin','player','forum')]
    [string]$Mode = 'admin',
    [int]$AppPort = 5003
)

$ErrorActionPreference = 'Stop'
$runner = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
if (-not (Test-Path $runner)) {
    throw "Missing runner: $runner"
}

Write-Host "[DEPRECATED SCRIPT] run_waitress.ps1 已收敛为门户入口包装器，请改用 run_portal_waitress.ps1。"
& $runner -AppDir $AppDir -Mode $Mode -AppPort $AppPort
exit $LASTEXITCODE
