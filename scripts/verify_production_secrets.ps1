#Requires -Version 5.1
param([switch]$ExpectFail)

$ErrorActionPreference = "Stop"
$Core = Join-Path (Split-Path -Parent $PSScriptRoot) "portals\common\core"
Push-Location $Core
try {
    $prev = $env:APP_ENV
    $env:APP_ENV = "production"
    $ErrorActionPreference = "Continue"
    & py -3 -c "from config import require_production_secrets; require_production_secrets(); print('ok')" 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($null -ne $prev) { $env:APP_ENV = $prev } else { Remove-Item Env:APP_ENV -ErrorAction SilentlyContinue }
    if ($ExpectFail) {
        if ($code -eq 0) { throw "expected fail-fast but secrets passed" }
        Write-Host "verify_production_secrets: fail-fast OK (as expected without secrets)"
        exit 0
    }
    if ($code -ne 0) {
        throw "require_production_secrets failed — set secrets per docs/runbooks/production_secrets.md"
    }
    $relay = [string]($env:CLUSTER_RELAY_TOKEN).Trim()
    if ($relay -eq "ma-cluster-relay-dev") {
        throw "CLUSTER_RELAY_TOKEN must not be ma-cluster-relay-dev in production (see production_secrets.md)"
    }
    Write-Host "verify_production_secrets PASS"
} finally {
    Pop-Location
}
