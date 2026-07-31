#Requires -Version 5.1
<#
.SYNOPSIS
  DevStack full closure E2E: stack health → bootstrap → optional quick-publish path.
  Closes GAP-E2E-DEV-01, GAP-P1-02-E2E-02, GAP-P1-04-E2E-01
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [switch]$SkipDevStackStart,
    [int]$MaxDurationSec = 1800
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Core = Join-Path $Root "portals\common\core"
$started = Get-Date

function Write-Evidence($gapId, $exitCode, $cmd, $notes) {
    py -3 -c @"
import sys
sys.path.insert(0, r'$Core')
from scripts.closure_evidence import write_evidence
write_evidence('$gapId', command='$cmd', exit_code=$exitCode, notes='$notes')
"@ | Out-Null
}

if (-not $SkipDevStackStart) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\Start-DevStack.ps1") -SkipBuild
}

py -3 (Join-Path $Core "scripts\seed_release_gate_fixture.py") --force-update
if ($LASTEXITCODE -ne 0) { throw "seed failed" }

py -3 (Join-Path $Core "scripts\bootstrap_gate_e2e.py")
if ($LASTEXITCODE -ne 0) { throw "bootstrap_gate_e2e failed" }

$health = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 10
if ($health.StatusCode -ne 200) { throw "health not 200" }

$elapsed = [int]((Get-Date) - $started).TotalSeconds
if ($elapsed -gt $MaxDurationSec) { throw "exceeded ${MaxDurationSec}s (took ${elapsed}s)" }

Write-Evidence "GAP-E2E-DEV-01" 0 "run_devstack_full_closure_e2e.ps1" "bootstrap chain OK"
Write-Evidence "GAP-P1-02-E2E-02" 0 "run_devstack_full_closure_e2e.ps1" "duration_sec=$elapsed"
Write-Evidence "GAP-P1-04-E2E-01" 0 "bootstrap_gate_e2e after DevStack" "dev path smoke"
Write-Host "run_devstack_full_closure_e2e PASS (${elapsed}s)" -ForegroundColor Green
