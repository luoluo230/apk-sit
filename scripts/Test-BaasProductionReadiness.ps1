#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$CheckDocker,
    [switch]$RequireEnvironmentSecrets,
    [switch]$RequirePostgres
)
$ErrorActionPreference = "Stop"; $failed = 0
function Check([string]$Name, [bool]$Passed, [string]$Detail) { if ($Passed) { Write-Host "[OK] $Name - $Detail" } else { Write-Host "[FAIL] $Name - $Detail" -ForegroundColor Red; $script:failed++ } }
$compose = Join-Path $RepoRoot "docker-compose.baas.production.yml"
$migration = Join-Path $RepoRoot "portals\common\core\models\baas_migrations.py"
$backup = Join-Path $RepoRoot "scripts\Backup-PortalData.ps1"
$entry = Join-Path $RepoRoot "portals\common\core\app_baas.py"
Check "production compose" (Test-Path $compose) $compose
Check "BaaS migration registry" (Test-Path $migration) $migration
Check "backup tool" (Test-Path $backup) $backup
Check "BaaS entry point" (Test-Path $entry) $entry
if ($RequireEnvironmentSecrets) {
    foreach ($name in @("BAAS_POSTGRES_USER", "BAAS_POSTGRES_PASSWORD", "BAAS_POSTGRES_DB", "BAAS_SECRET_KEY")) { Check "secret $name" (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) "environment variable" }
}
if ($RequirePostgres) {
    $checkScript = Join-Path $RepoRoot "portals\common\core\scripts\db_readiness_check.py"
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { Check "PostgreSQL runtime gate" $false "Python launcher 'py' not found" }
    else {
        & py -3 $checkScript --require-postgres
        Check "PostgreSQL runtime gate" ($LASTEXITCODE -eq 0) "DATABASE_URL must select PostgreSQL"
    }
}
if ($CheckDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Check "docker compose" $false "docker not found" }
    else { & docker compose -f $compose config --quiet; Check "docker compose render" ($LASTEXITCODE -eq 0) $compose }
}
if ($failed -gt 0) { exit 1 }; Write-Host "BaaS production readiness passed."; exit 0
