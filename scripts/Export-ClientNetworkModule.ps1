#Requires -Version 5.1
<#
.SYNOPSIS
  Export a standalone client network module zip (topology | baas).

.DESCRIPTION
  Each zip is self-contained. Import into Unity via Import-ClientNetworkModule.ps1.
  Base project keeps only packages/client_network/stubs until modules are imported.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Export-ClientNetworkModule.ps1 -Module baas
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("topology", "baas")]
    [string]$Module,
    [string]$OutputPath = "",
    [string]$MaclientRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pkgRoot = Join-Path $repoRoot "packages/client_network/$Module"
$manifestPath = Join-Path $pkgRoot "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "Missing manifest: $manifestPath" }

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path $repoRoot "dist/client-network-$Module-$stamp.zip"
}
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force }

$temp = Join-Path ([IO.Path]::GetTempPath()) ("client_network_export_" + [Guid]::NewGuid().ToString("N"))
$bundle = Join-Path $temp "ClientNetworkModule"
New-Item -ItemType Directory -Path $bundle -Force | Out-Null

Copy-Item $manifestPath (Join-Path $bundle "manifest.json")
Copy-Item (Join-Path $repoRoot "packages/client_network/stubs") (Join-Path $bundle "stubs") -Recurse -Force
Copy-Item (Join-Path $pkgRoot "Runtime") (Join-Path $bundle "Runtime") -Recurse -Force

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$asmdefName = $manifest.asmdef
$asmdefPath = Join-Path $bundle "$asmdefName"
@"
{
  "name": "$($asmdefName -replace '\.asmdef$','')",
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
"@ | Set-Content -Path $asmdefPath -Encoding UTF8

if ($Module -eq "topology" -and -not [string]::IsNullOrWhiteSpace($MaclientRoot) -and (Test-Path $MaclientRoot)) {
    foreach ($rel in @($manifest.maclient_export_roots)) {
        $src = Join-Path $MaclientRoot ($rel -replace '/', '\')
        if (Test-Path $src) {
            $dest = Join-Path $bundle ("maclient/" + $rel)
            $parent = Split-Path $dest -Parent
            if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            if (Test-Path $src -PathType Container) {
                Copy-Item $src $dest -Recurse -Force
            } else {
                Copy-Item $src $dest -Force
                if (Test-Path ($src + ".meta")) { Copy-Item ($src + ".meta") ($dest + ".meta") -Force }
            }
        }
    }
}

$readme = @"
# Client Network Module: $Module
Pairs with: $($manifest.pairs_with)
Import target: $($manifest.import_target)

1. Unzip to a temp folder.
2. Run Import-ClientNetworkModule.ps1 -Module $Module -SourceDir <unzipped>
3. Unity will compile assembly $($manifest.namespace).
"@
Set-Content -Path (Join-Path $bundle "README_IMPORT.md") -Value $readme -Encoding UTF8

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($bundle, $OutputPath)
Remove-Item $temp -Recurse -Force
Write-Host "[export] wrote $OutputPath" -ForegroundColor Green
