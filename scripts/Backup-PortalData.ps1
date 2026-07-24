#Requires -Version 5.1
<#
.SYNOPSIS
  Package Portal data for backup. Plan P0-01 Step 6.
.EXAMPLE
  powershell -File scripts/Backup-PortalData.ps1 -DryRun
  powershell -File scripts/Backup-PortalData.ps1 -OutputDir D:\backups\apk-site
#>
param(
    [string]$OutputDir = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DataDir = Join-Path $Root "data"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Dest = if ($OutputDir) { Join-Path $OutputDir "apk-site-backup-$Stamp" } else { Join-Path $Root "tmp/backups/apk-site-backup-$Stamp" }

$Include = @(
    (Join-Path $DataDir "apk_site.db"),
    (Join-Path $DataDir "projects.json"),
    (Join-Path $DataDir "channels.json"),
    (Join-Path $DataDir "project_versions.json"),
    (Join-Path $DataDir "jenkins_instances.json")
)
$JenkinsRoot = Join-Path $DataDir "jenkins_instances"

Write-Host "Backup source: $DataDir"
Write-Host "Destination:   $Dest"

if ($DryRun) {
    foreach ($p in $Include) {
        if (Test-Path $p) { Write-Host "[dry-run] file $p" }
    }
    if (Test-Path $JenkinsRoot) {
        Get-ChildItem -Path $JenkinsRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "[dry-run] jenkins instance $($_.Name)"
        }
    }
    Write-Host "Dry run complete."
    exit 0
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach ($p in $Include) {
    if (Test-Path $p) {
        Copy-Item -Path $p -Destination $Dest -Force
    }
}
if (Test-Path $JenkinsRoot) {
    $jenkinsDest = Join-Path $Dest "jenkins_instances"
    New-Item -ItemType Directory -Force -Path $jenkinsDest | Out-Null
    Get-ChildItem -Path $JenkinsRoot -Directory | ForEach-Object {
        $instance = $_
        $target = Join-Path $jenkinsDest $instance.Name
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        foreach ($name in @("config.xml", ".apk-site-env", "scripts")) {
            $src = Join-Path $instance.FullName $name
            if (Test-Path $src) {
                Copy-Item -Path $src -Destination (Join-Path $target $name) -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

$zip = "$Dest.zip"
Compress-Archive -Path $Dest -DestinationPath $zip -Force
Write-Host "Backup written: $zip"
