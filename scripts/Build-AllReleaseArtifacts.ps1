#Requires -Version 5.1
<#
.SYNOPSIS
  Build server deploy zips + client network module zips into dist/.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Build-AllReleaseArtifacts.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Build-AllReleaseArtifacts.ps1 -MaclientRoot E:\maclient
#>
param(
    [string]$ApkSiteRoot = "",
    [string]$MaclientRoot = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) { $ApkSiteRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path }
if (-not $OutputDir) { $OutputDir = Join-Path $ApkSiteRoot "dist" }
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

$core = Join-Path $ApkSiteRoot "portals\common\core"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "=== Build-AllReleaseArtifacts ===" -ForegroundColor Cyan
Write-Host "  repo:   $ApkSiteRoot"
Write-Host "  output: $OutputDir"
Write-Host "  stamp:  $stamp"

# --- Server deploy packs ---
Push-Location $core
$py = @"
import json, os, sys
sys.path.insert(0, os.getcwd())
from services.server_management.deploy_pack_service import build_deploy_pack
out = r'$OutputDir'.replace('\\\\', '/')
os.makedirs(out, exist_ok=True)
manifest = {'generated_at': '$stamp', 'artifacts': []}
for kind in ('topology', 'baas'):
    blob, name = build_deploy_pack(kind)
    path = os.path.join(out, name.replace('.zip', '') + '-$stamp.zip')
    with open(path, 'wb') as f:
        f.write(blob)
    manifest['artifacts'].append({'type': 'server_deploy', 'kind': kind, 'file': os.path.basename(path), 'bytes': len(blob)})
    print(f'[server] {path} ({len(blob)} bytes)')
with open(os.path.join(out, 'release-manifest-$stamp.json'), 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
"@
& py -3 -c $py
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "deploy pack build failed" }
Pop-Location

# --- Client network module zips ---
$exportScript = Join-Path $ApkSiteRoot "scripts\Export-ClientNetworkModule.ps1"
foreach ($mod in @("topology", "baas")) {
    $outZip = Join-Path $OutputDir "client-network-$mod-$stamp.zip"
    $args = @("-Module", $mod, "-OutputPath", $outZip)
    if ($mod -eq "topology" -and -not [string]::IsNullOrWhiteSpace($MaclientRoot)) {
        $args += @("-MaclientRoot", $MaclientRoot)
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $exportScript @args
    if ($LASTEXITCODE -ne 0) { throw "export $mod failed" }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Get-ChildItem $OutputDir -Filter "*$stamp*" | ForEach-Object {
    Write-Host ("  {0,-55} {1,10:N0} bytes" -f $_.Name, $_.Length)
}
