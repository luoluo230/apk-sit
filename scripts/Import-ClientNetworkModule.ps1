#Requires -Version 5.1
<#
.SYNOPSIS
  Import topology or baas client network module into maclient.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 -Module baas
  powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 -Module baas -Remove
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("topology", "baas")]
    [string]$Module,
    [string]$MaclientRoot = "",
    [string]$SourceDir = "",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

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

$repoRoot = Split-Path -Parent $PSScriptRoot
$maclient = Resolve-MaclientRoot $MaclientRoot
$pkgRoot = if ($SourceDir) { $SourceDir } else { Join-Path $repoRoot "packages/client_network/$Module" }
$manifest = Get-Content (Join-Path $pkgRoot "manifest.json") -Raw | ConvertFrom-Json
$targetRel = if ($Module -eq "baas") { "Assets/Modules/BaasNetwork" } else { "Assets/Modules/TopologyNetwork" }
$target = Join-Path $maclient ($targetRel -replace '/', '\')

if ($Remove) {
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Write-Host "[import] removed $targetRel" -ForegroundColor Yellow
} else {
    if (-not (Test-Path $pkgRoot)) { throw "Source not found: $pkgRoot" }
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item (Join-Path $pkgRoot "Runtime") (Join-Path $target "Runtime") -Recurse -Force
    if (Test-Path (Join-Path $pkgRoot "$($manifest.asmdef)")) {
        Copy-Item (Join-Path $pkgRoot "$($manifest.asmdef)") (Join-Path $target "$($manifest.asmdef)") -Force
    } else {
        $asm = "$($manifest.asmdef)"
        @"
{
  "name": "$($asm -replace '\.asmdef$','')",
  "rootNamespace": "$($manifest.namespace)",
  "references": [],
  "includePlatforms": [],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "autoReferenced": true,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
"@ | Set-Content -Path (Join-Path $target $asm) -Encoding UTF8
    }
    if ($Module -eq "topology" -and (Test-Path (Join-Path $pkgRoot "maclient"))) {
        Copy-Item (Join-Path $pkgRoot "maclient/*") $maclient -Recurse -Force
    }
}

$stubsSrc = Join-Path $repoRoot "packages/client_network/stubs/Runtime"
$stubsDest = Join-Path $maclient "Assets/Src/HotUpdate/Framework/Network/Abstractions"
if ((-not $Remove) -and (Test-Path $stubsSrc)) {
    if (-not (Test-Path $stubsDest)) { New-Item -ItemType Directory -Path $stubsDest -Force | Out-Null }
    Copy-Item (Join-Path $stubsSrc "ClientNetworkModuleGate.cs") (Join-Path $stubsDest "ClientNetworkModuleGate.cs") -Force
    @"
{
  "name": "MAClient.Network.Abstractions",
  "rootNamespace": "MAClient.Network.Abstractions",
  "references": [],
  "includePlatforms": [],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "autoReferenced": true,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
"@ | Set-Content -Path (Join-Path $stubsDest "MAClient.Network.Abstractions.asmdef") -Encoding UTF8
}

$manifestPath = Join-Path $maclient "Assets/StreamingAssets/client_network_modules.json"
$rows = @{ modules = @() }
if (Test-Path $manifestPath) {
    try { $rows = Get-Content $manifestPath -Raw | ConvertFrom-Json } catch { }
}
$map = @{}
foreach ($row in @($rows.modules)) { if ($row.key) { $map[$row.key] = $row } }
if ($Remove) {
    if ($map.ContainsKey($Module)) { $map[$Module].installed = $false }
} else {
    $map[$Module] = [pscustomobject]@{ key = $Module; installed = $true; imported_at = (Get-Date).ToString("o") }
}
$out = @{ modules = @($map.Values) } | ConvertTo-Json -Depth 4
$streamDir = Split-Path $manifestPath -Parent
if (-not (Test-Path $streamDir)) { New-Item -ItemType Directory -Path $streamDir -Force | Out-Null }
Set-Content -Path $manifestPath -Value $out -Encoding UTF8
Write-Host "[import] module=$Module target=$targetRel remove=$Remove" -ForegroundColor Green
