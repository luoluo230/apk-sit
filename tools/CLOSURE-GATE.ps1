#Requires -Version 5.1
<#
.SYNOPSIS
  Single closure acceptance gate for arch-docs Plane.

.EXAMPLE
  $env:CLOSURE_MODE = "1"
  powershell -File tools\CLOSURE-GATE.ps1
  powershell -File tools\CLOSURE-GATE.ps1 -SkipUnity -SkipDocker
#>
param(
    [switch]$SkipUnity,
    [switch]$SkipDocker,
    [switch]$SkipGameServer,
    [switch]$DevSkip,
    [string]$UnityScenario = "smoke",
    [string]$BaseUrl = "http://127.0.0.1:5003"
)

$ErrorActionPreference = "Stop"
$env:CLOSURE_MODE = "1"
if ($DevSkip) {
    $env:JENKINS_GATE_DEV_SKIP = "1"
} else {
    Remove-Item Env:JENKINS_GATE_DEV_SKIP -ErrorAction SilentlyContinue
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Core = Join-Path $Root "portals\common\core"

Write-Host "=== CLOSURE GATE (arch-docs Plane) ===" -ForegroundColor Cyan

& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "start_release_stack.ps1") `
    -ApkSiteRoot $Root `
    -AllServers `
    @($(if ($SkipDocker) { "-SkipDocker" })) `
    @($(if ($SkipGameServer) { "-SkipGameServer" }))

Push-Location $Core
try {
    py -3 scripts\seed_release_gate_fixture.py --force-update --rollout-percentage 50
    if ($LASTEXITCODE -ne 0) { throw "seed --force-update failed" }

    $env:REQUIRE_FORCE_UPDATE = "1"
    py -3 scripts\bootstrap_gate_e2e.py
    if ($LASTEXITCODE -ne 0) { throw "bootstrap_gate_e2e failed" }

    py -3 scripts\redis_session_gate.py
    if ($LASTEXITCODE -ne 0) { throw "redis_session_gate failed" }

    py -3 scripts\webhook_feishu_gate.py
    if ($LASTEXITCODE -ne 0) { throw "webhook_feishu_gate failed" }

    py -3 scripts\jenkins_presence_gate.py
    if ($LASTEXITCODE -ne 0) { throw "jenkins_presence_gate failed" }

    py -3 scripts\sqlite_primary_gate.py
    if ($LASTEXITCODE -ne 0) { throw "sqlite_primary_gate failed" }

    py -3 scripts\reports_dashboard_gate.py
    if ($LASTEXITCODE -ne 0) { throw "reports_dashboard_gate failed" }

    py -3 scripts\rbac_dynamic_ui_gate.py
    if ($LASTEXITCODE -ne 0) { throw "rbac_dynamic_ui_gate failed" }

    py -3 scripts\notifications_stream_gate.py
    if ($LASTEXITCODE -ne 0) { throw "notifications_stream_gate failed" }

    py -3 scripts\tls_readiness_gate.py
    if ($LASTEXITCODE -ne 0) { throw "tls_readiness_gate failed" }

    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\host_full_stack_gate.ps1")
    if ($LASTEXITCODE -ne 0) { throw "host_full_stack_gate failed" }

    & powershell -ExecutionPolicy Bypass -File (Join-Path $Core "scripts\pressure_s1_s2_gate.ps1")
    if ($LASTEXITCODE -ne 0) { throw "pressure_s1_s2_gate failed" }

    py -3 scripts\ops_platform_e2e_gate.py
    if ($LASTEXITCODE -ne 0) { throw "ops_platform_e2e_gate failed" }

    py -3 -m pytest tests\ -q
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

    py -3 scripts\commercial_startup_sequence_gate.py
    if ($LASTEXITCODE -ne 0) { throw "commercial_startup_sequence_gate failed" }

    py -3 scripts\transport_login_matrix.py
    if ($LASTEXITCODE -ne 0) { throw "transport_login_matrix failed" }

    py -3 scripts\gameserver_cluster_gate.py
    if ($LASTEXITCODE -ne 0) { throw "gameserver_cluster_gate failed" }

    if (-not $SkipDocker) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\docker_compose_smoke_gate.ps1")
        if ($LASTEXITCODE -ne 0) { throw "docker_compose_smoke_gate failed" }
    }

    $splitScript = Join-Path $Core "scripts\verify_split_bundles_runtime.ps1"
    $bundlesRoot = Join-Path $Core "release_bundles\admin-backend\start_admin.ps1"
    if ((Test-Path $splitScript) -and (Test-Path $bundlesRoot)) {
        & powershell -ExecutionPolicy Bypass -File $splitScript -SkipInstall
        if ($LASTEXITCODE -ne 0) { throw "verify_split_bundles_runtime failed" }
    } else {
        Write-Warning "split bundles skipped (T-F04 partial: release_bundles not built)"
    }

    $i18n = Join-Path $Root "scripts\i18n_coverage_gate.py"
    if (Test-Path $i18n) {
        py -3 $i18n
        if ($LASTEXITCODE -ne 0) { throw "i18n_coverage_gate failed" }
    }

    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "tools\unified_release_ci.ps1") `
        -RequireStack -SkipUnity
    if ($LASTEXITCODE -ne 0) { throw "unified_release_ci failed" }

    if (-not $SkipUnity) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "tools\unified_release_ci.ps1") `
            -RequireStack -SkipServer -UnityScenario smoke
        if ($LASTEXITCODE -ne 0) { throw "Unity smoke failed" }
        & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "tools\unified_release_ci.ps1") `
            -RequireStack -SkipServer -UnityScenario session
        if ($LASTEXITCODE -ne 0) { throw "Unity session failed" }
    }
} finally {
    Pop-Location
}

$evidence = Join-Path $Root "docs\evidence\$(Get-Date -Format yyyy-MM-dd)"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
"CLOSURE GATE PASSED $(Get-Date -Format o)" | Set-Content (Join-Path $evidence "closure-gate.log") -Encoding UTF8
Write-Host "=== CLOSURE GATE PASSED ===" -ForegroundColor Green
Write-Host "Evidence: $evidence"
