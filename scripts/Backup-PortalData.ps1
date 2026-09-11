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
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [int]$RetainCount = 14,
    [switch]$RequirePostgres,
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

function Resolve-PgTool([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $roots = @("C:\Program Files\PostgreSQL", "C:\Program Files (x86)\PostgreSQL")
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            $candidate = Get-ChildItem -LiteralPath $root -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($candidate) { return $candidate.FullName }
        }
    }
    return $null
}

function Write-BackupManifest([string]$Path) {
    $files = Get-ChildItem -LiteralPath $Path -File -Recurse | Where-Object { $_.Name -ne "manifest.json" } |
        ForEach-Object {
            [ordered]@{
                path = $_.FullName.Substring($Path.Length).TrimStart([char[]]'\\/')
                bytes = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    [ordered]@{
        schemaVersion = 2
        createdAtUtc = [DateTime]::UtcNow.ToString("o")
        databaseBackend = if ($DatabaseUrl) { "postgresql" } else { "sqlite" }
        files = @($files)
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Path "manifest.json") -Encoding UTF8
}

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
    if ($DatabaseUrl) {
        if ($DatabaseUrl -notmatch '^postgres(?:ql)?://') { throw "DatabaseUrl must be a PostgreSQL URL" }
        $pgDump = Resolve-PgTool "pg_dump"
        if (-not $pgDump) { throw "pg_dump.exe is required for a PostgreSQL backup" }
        Write-Host "[dry-run] PostgreSQL custom dump -> database.postgres.dump"
    } elseif ($RequirePostgres) {
        throw "-RequirePostgres requires DATABASE_URL or -DatabaseUrl"
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

if ($DatabaseUrl) {
    if ($DatabaseUrl -notmatch '^postgres(?:ql)?://') { throw "DatabaseUrl must be a PostgreSQL URL" }
    $pgDump = Resolve-PgTool "pg_dump"
    if (-not $pgDump) { throw "pg_dump.exe is required for a PostgreSQL backup" }
    $dumpPath = Join-Path $Dest "database.postgres.dump"
    & $pgDump "--dbname=$DatabaseUrl" --format=custom --no-owner --no-privileges "--file=$dumpPath"
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $dumpPath)) { throw "pg_dump failed" }
} elseif ($RequirePostgres) {
    throw "-RequirePostgres requires DATABASE_URL or -DatabaseUrl"
}

Write-BackupManifest $Dest

$zip = "$Dest.zip"
Compress-Archive -Path $Dest -DestinationPath $zip -Force
Write-Host "Backup written: $zip"

if ($RetainCount -gt 0) {
    $parent = Split-Path -Parent $Dest
    Get-ChildItem -LiteralPath $parent -Filter "apk-site-backup-*.zip" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending | Select-Object -Skip $RetainCount |
        Remove-Item -Force -ErrorAction Stop
}
