#Requires -Version 5.1
<#
.SYNOPSIS
  One-click standalone Casual BaaS stack (Portal + DB init, optional Postgres).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -UsePostgres -Background
#>
param(
    [string]$ApkSiteRoot = "",
    [int]$Port = 5004,
    [string]$BindHost = "127.0.0.1",
    [switch]$Background,
    [switch]$UsePostgres,
    [switch]$SkipCleanup
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
}

$core = Join-Path $ApkSiteRoot "portals\common\core"
$runner = Join-Path $core "scripts\run_baas_server.ps1"
$compose = Join-Path $ApkSiteRoot "docker-compose.baas.yml"

Write-Host "=== Start-BaaSStack (standalone Casual BaaS) ===" -ForegroundColor Cyan

$env:BAAS_STANDALONE = "1"
$env:PORTAL_SERVER_FRAMEWORKS = "baas"
$env:BAAS_PORT = "$Port"
$env:BAAS_HOST = $BindHost

if ($UsePostgres) {
    if (-not (Test-Path $compose)) { throw "Missing $compose" }
    Write-Host "[baas] starting PostgreSQL via docker compose..." -ForegroundColor Yellow
    docker compose -f $compose up -d postgres
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
    $env:DATABASE_URL = "postgresql://apk_baas:apk_baas_dev@127.0.0.1:5433/apk_baas"
    Write-Host "[baas] DATABASE_URL set (port 5433)" -ForegroundColor DarkGray
} else {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Write-Host "[baas] using SQLite (data/apk_site.db)" -ForegroundColor DarkGray
}

Write-Host "[baas] initializing database schema..."
Push-Location $core
& py -3 -c "from models.db import init_db; init_db(); print('init_db OK')"
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "init_db failed" }
Pop-Location

if ($Background) {
    Write-Host "[baas] launching background server on ${BindHost}:$Port" -ForegroundColor Cyan
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runner,
        "-Port", $Port, "-BindHost", $BindHost
    ) -WorkingDirectory $core -PassThru -WindowStyle Minimized
    Write-Host "[baas] launcher pid=$($proc.Id)" -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(90)
    $ok = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://${BindHost}:$Port/health" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { Start-Sleep -Seconds 2 }
    }
    if (-not $ok) { throw "BaaS health check timeout" }
} else {
    Write-Host "[baas] starting foreground server (Ctrl+C to stop)" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Port $Port -BindHost $BindHost
    exit $LASTEXITCODE
}

$base = "http://${BindHost}:$Port"
Write-Host ""
Write-Host "=== BaaS Stack Ready ===" -ForegroundColor Green
Write-Host "  Admin:      $base/admin/baas"
Write-Host "  Login:      $base/login"
Write-Host "  Health:     $base/health"
Write-Host "  Bootstrap:  $base/api/public/client-bootstrap?game_id=&game_key=&env=development"
Write-Host "  Client pkg: packages/client_network/baas/"
Write-Host ""
