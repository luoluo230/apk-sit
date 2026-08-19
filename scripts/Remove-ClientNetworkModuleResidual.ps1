#Requires -Version 5.1
<#
.SYNOPSIS
  Remove imported client network module code from maclient (keep Abstractions gate only).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Remove-ClientNetworkModuleResidual.ps1 -MaclientRoot E:\maclient
#>
param(
    [string]$MaclientRoot = "",
    [switch]$SkipBaasBootstrap
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$importScript = Join-Path $repoRoot "scripts\Import-ClientNetworkModule.ps1"

function Resolve-MaclientRoot([string]$Candidate) {
    if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path $Candidate)) {
        return (Resolve-Path $Candidate).Path
    }
    foreach ($path in @($env:MACLIENT_ROOT, $env:UNITY_PROJECT_PATH, "E:\maclient")) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return (Resolve-Path $path).Path
        }
    }
    throw "maclient root not found"
}

$maclient = Resolve-MaclientRoot $MaclientRoot
Write-Host "=== Remove-ClientNetworkModuleResidual ===" -ForegroundColor Cyan
Write-Host "  maclient: $maclient"

foreach ($mod in @("baas", "topology")) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $importScript -Module $mod -MaclientRoot $maclient -Remove
}

$removePaths = @(
    "Assets/Modules/BaasNetwork",
    "Assets/Modules/TopologyNetwork"
)
foreach ($rel in $removePaths) {
    $full = Join-Path $maclient ($rel -replace '/', '\')
    if (Test-Path $full) {
        Remove-Item $full -Recurse -Force
        Write-Host "[remove] $rel" -ForegroundColor Yellow
    }
}

if (-not $SkipBaasBootstrap) {
    foreach ($rel in @(
        "Assets/Src/HotUpdate/Framework/Bootstrap/BaasBootstrapService.cs",
        "Assets/Src/HotUpdate/Framework/Bootstrap/BaasBootstrapContracts.cs",
        "Assets/Editor/Tests/BaasBootstrapContractFixtureTests.cs"
    )) {
        $full = Join-Path $maclient ($rel -replace '/', '\')
        if (Test-Path $full) {
            Remove-Item $full -Force
            $meta = $full + ".meta"
            if (Test-Path $meta) { Remove-Item $meta -Force }
            Write-Host "[remove] $rel" -ForegroundColor Yellow
        }
    }
}

$manifestPath = Join-Path $maclient "Assets/StreamingAssets/client_network_modules.json"
$emptyManifest = @{ modules = @() } | ConvertTo-Json -Depth 4
Set-Content -Path $manifestPath -Value $emptyManifest -Encoding UTF8
Write-Host "[reset] client_network_modules.json" -ForegroundColor Green

Write-Host "=== Done — maclient retains Abstractions gate only ===" -ForegroundColor Green
