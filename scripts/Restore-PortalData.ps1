#Requires -Version 5.1
<#
.SYNOPSIS
  Verify and restore an apk-site backup. Writes require -ConfirmRestore.
#>
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [string]$DestinationRoot = "",
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Resolve-PgTool([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($root in @("C:\Program Files\PostgreSQL", "C:\Program Files (x86)\PostgreSQL")) {
        if (Test-Path -LiteralPath $root) {
            $candidate = Get-ChildItem -LiteralPath $root -Recurse -Filter "$Name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($candidate) { return $candidate.FullName }
        }
    }
    return $null
}

$resolved = (Resolve-Path -LiteralPath $BackupPath).Path
$scratch = ""
if ((Get-Item -LiteralPath $resolved).PSIsContainer) {
    $source = $resolved
} elseif ([IO.Path]::GetExtension($resolved) -eq ".zip") {
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ("apk-site-restore-" + [Guid]::NewGuid().ToString("N"))
    Expand-Archive -LiteralPath $resolved -DestinationPath $scratch -Force
    $source = Get-ChildItem -LiteralPath $scratch -Directory | Select-Object -First 1 -ExpandProperty FullName
    if (-not $source) { throw "Backup archive has no backup directory" }
} else { throw "BackupPath must be a backup directory or zip" }

try {
    $manifestPath = Join-Path $source "manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "manifest.json is required" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($entry in $manifest.files) {
        $candidate = Join-Path $source $entry.path
        if (-not (Test-Path -LiteralPath $candidate)) { throw "Backup file missing: $($entry.path)" }
        $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $entry.sha256) { throw "Backup checksum mismatch: $($entry.path)" }
    }
    Write-Host "Backup manifest verified: $($manifest.files.Count) files"
    if (-not $ConfirmRestore) { Write-Host "Dry run complete. Re-run with -ConfirmRestore to write data."; exit 0 }

    $target = if ($DestinationRoot) { $DestinationRoot } else { $Root }
    $dataSource = Join-Path $source "apk_site.db"
    if (Test-Path -LiteralPath $dataSource) {
        $dataTarget = Join-Path $target "data\apk_site.db"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dataTarget) | Out-Null
        Copy-Item -LiteralPath $dataSource -Destination $dataTarget -Force
    }
    $dump = Join-Path $source "database.postgres.dump"
    if (Test-Path -LiteralPath $dump) {
        if (-not $DatabaseUrl -or $DatabaseUrl -notmatch '^postgres(?:ql)?://') { throw "PostgreSQL backup requires DATABASE_URL or -DatabaseUrl" }
        $pgRestore = Resolve-PgTool "pg_restore"
        if (-not $pgRestore) { throw "pg_restore.exe is required" }
        & $pgRestore "--dbname=$DatabaseUrl" --clean --if-exists --no-owner --no-privileges $dump
        if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }
    }
    Write-Host "Restore completed. Restart the Portal and validate /health before reopening traffic."
} finally {
    if ($scratch -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
