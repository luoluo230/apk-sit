#Requires -Version 5.1
<#
.SYNOPSIS
  Sync unity_contract_manifest.json into maclient StreamingAssets for EditMode tests.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Sync-UnityContractManifest.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Sync-UnityContractManifest.ps1 -PortalBaseUrl http://127.0.0.1:5003
#>
param(
    [string]$MaclientRoot = "",
    [string]$PortalBaseUrl = "http://127.0.0.1:5003",
    [switch]$LocalOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$CoreRoot = Join-Path $RepoRoot "portals\common\core"
$SyncPy = Join-Path $CoreRoot "scripts\sync_unity_contract_manifest.py"

function Resolve-MaclientRoot([string]$Candidate) {
    if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path $Candidate)) {
        return (Resolve-Path $Candidate).Path
    }
    foreach ($path in @($env:MACLIENT_ROOT, $env:UNITY_PROJECT_PATH, "E:\maclient")) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return (Resolve-Path $path).Path
        }
    }
    throw "maclient root not found. Set MACLIENT_ROOT or pass -MaclientRoot."
}

$macRoot = Resolve-MaclientRoot $MaclientRoot
$destDir = Join-Path $macRoot "Assets\StreamingAssets"
$destFile = Join-Path $destDir "unity_contract_manifest.json"
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$args = @($SyncPy, "--dest", $destFile)
if ($LocalOnly) {
    $args += @("--local-only")
} else {
    $args += @("--portal-base-url", $PortalBaseUrl)
}

& py -3 @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Synced unity contract manifest -> $destFile"
