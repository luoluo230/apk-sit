#Requires -Version 5.1
param(
    [string]$ProjectId = "GomeKu",
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [switch]$SkipDevStackStart
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Core = Join-Path $RepoRoot "portals\common\core"

if (-not $SkipDevStackStart) {
    Write-Host "Starting DevStack..." -ForegroundColor Cyan
    & (Join-Path $RepoRoot "scripts\Start-DevStack.ps1") -SkipBuild
    if ($LASTEXITCODE -ne 0) { throw "Start-DevStack failed" }
}

Push-Location $Core
try {
    py -3 -m pytest tests/test_server_release.py -q
    if ($LASTEXITCODE -ne 0) { throw "test_server_release failed" }

    py -3 scripts/server_release_devstack_e2e.py --base-url $BaseUrl --project-id $ProjectId --write-evidence
    if ($LASTEXITCODE -ne 0) { throw "server_release_devstack_e2e failed" }

    Write-Host "run_server_release_devstack_e2e PASS" -ForegroundColor Green
} finally {
    Pop-Location
}
