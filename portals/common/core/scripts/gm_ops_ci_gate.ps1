param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Env = "staging",
    [string]$Channel = "test",
    [string]$Platform = "android",
    [string]$VersionName = "",
    [string]$ScopeId = "gomeku:production:1001",
    [Parameter(Mandatory = $true)][string]$CiToken
)

$ErrorActionPreference = "Stop"

$uri = "$BaseUrl/api/gm-ops/quality-gate/ci?project_id=$ProjectId&env=$Env&channel=$Channel&platform=$Platform&version_name=$VersionName&ci_token=$CiToken"

try {
    $resp = Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 30
} catch {
    Write-Error "质量门禁接口调用失败: $($_.Exception.Message)"
    exit 3
}

$resp | ConvertTo-Json -Depth 12

if (-not $resp.ok) {
    Write-Error "质量门禁未通过。"
    exit 4
}

Write-Output "质量门禁通过。"

$coreRoot = Join-Path (Split-Path $PSScriptRoot -Parent) "."
$releaseGate = Join-Path $coreRoot "scripts\release_platform_ci_gate.py"
$commercialGate = Join-Path $coreRoot "scripts\commercial_startup_sequence_gate.py"
if (Test-Path $releaseGate) {
    $env:RELEASE_CI_BASE_URL = $BaseUrl
    $env:RELEASE_CI_SCOPE_ID = $ScopeId
    $env:GM_CI_TOKEN = $CiToken
    & py -3 $releaseGate --base-url $BaseUrl --scope-id $ScopeId --ci-token $CiToken
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Release platform CI gate failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}
if (Test-Path $commercialGate) {
    $env:RELEASE_GATE_BASE_URL = $BaseUrl
    $env:RELEASE_GATE_SCOPE_ID = $ScopeId
    & py -3 $commercialGate
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Commercial startup sequence gate failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

exit 0
