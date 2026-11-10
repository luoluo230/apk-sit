#Requires -Version 5.1
<#
.SYNOPSIS
  P4-01 Wave A/B: one-click Casual BaaS deploy (deps check, env, stack, health).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Deploy-BaasOneClick.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Deploy-BaasOneClick.ps1 -UsePostgres -WithRedis -Workers 4 -Background
#>
param(
    [string]$ApkSiteRoot = "",
    [int]$Port = 5004,
    [string]$BindHost = "127.0.0.1",
    [switch]$UsePostgres,
    [switch]$WithRedis,
    [int]$Workers = 1,
    [int]$Nodes = 1,
    [switch]$Background,
    [switch]$SkipInstallHints
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
}
$core = Join-Path $ApkSiteRoot "portals\common\core"
$envFile = Join-Path $ApkSiteRoot ".env.baas.local"

Write-Host "=== Deploy-BaasOneClick (P4-01) ===" -ForegroundColor Cyan
Write-Host "root=$ApkSiteRoot"

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

$missing = @()
if (-not (Test-Cmd "py") -and -not (Test-Cmd "python")) { $missing += "Python 3.10+ (py launcher)" }
if (-not (Test-Cmd "git")) { $missing += "Git" }
if ($UsePostgres -or $WithRedis) {
    if (-not (Test-Cmd "docker")) { $missing += "Docker Desktop (for Postgres/Redis)" }
}
if ($missing.Count -gt 0 -and -not $SkipInstallHints) {
    Write-Host "[deps] missing:" -ForegroundColor Yellow
    $missing | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Install then re-run. Winget examples:" -ForegroundColor DarkYellow
    Write-Host "  winget install Python.Python.3.12 Git.Git Docker.DockerDesktop"
    if ($missing.Count -gt 0 -and -not (Test-Cmd "py") -and -not (Test-Cmd "python")) {
        throw "Python is required"
    }
}

$py = if (Test-Cmd "py") { "py" } else { "python" }
$pyArgs = if ($py -eq "py") { @("-3") } else { @() }

# Ensure .env.baas.local
if (-not (Test-Path $envFile)) {
    $secret = -join ((1..48) | ForEach-Object { "{0:x}" -f (Get-Random -Max 16) })
    @"
BAAS_STANDALONE=1
PORTAL_SERVER_FRAMEWORKS=baas
BAAS_PORT=$Port
BAAS_HOST=$BindHost
SECRET_KEY=$secret
BAAS_WORKERS=$Workers
"@ | Set-Content -Encoding utf8 $envFile
    Write-Host "[env] wrote $envFile" -ForegroundColor Green
} else {
    Write-Host "[env] reuse $envFile" -ForegroundColor DarkGray
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
    $k, $v = $line.Split("=", 2)
    Set-Item -Path "Env:$k" -Value $v
}

# pip deps (core requirements if present)
$req = Join-Path $core "requirements.txt"
if (-not (Test-Path $req)) { $req = Join-Path $ApkSiteRoot "requirements.txt" }
if (Test-Path $req) {
    Write-Host "[pip] $req"
    & $py @pyArgs -m pip install -q -r $req
}

if ($WithRedis -and (Test-Cmd "docker")) {
    Write-Host "[redis] ensuring redis:7 ..."
    docker rm -f baas-redis 2>$null | Out-Null
    docker run -d --name baas-redis -p 6379:6379 redis:7-alpine | Out-Null
    $env:REDIS_URL = "redis://127.0.0.1:6379/0"
    Add-Content -Path $envFile -Value "REDIS_URL=$($env:REDIS_URL)" -ErrorAction SilentlyContinue
}

if ($Nodes -gt 1) {
    Write-Host "[scale] Nodes=$Nodes → docker-compose.baas.scale.yml"
    $scale = Join-Path $ApkSiteRoot "docker-compose.baas.scale.yml"
    if (-not (Test-Path $scale)) { throw "Missing $scale" }
    if (-not (Test-Cmd "docker")) { throw "Docker required for -Nodes > 1" }
    docker compose -f $scale up -d --scale baas-portal=$Nodes
    if ($LASTEXITCODE -ne 0) { throw "scale compose failed" }
} else {
    # Start stack via existing helper
    $start = Join-Path $scriptRoot "Start-BaaSStack.ps1"
    $startArgs = @{
        ApkSiteRoot = $ApkSiteRoot
        Port        = $Port
        BindHost    = $BindHost
        Background  = $Background
    }
    if ($UsePostgres) { $startArgs.UsePostgres = $true }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $start @startArgs
    if ($LASTEXITCODE -ne 0) { throw "Start-BaaSStack failed: $LASTEXITCODE" }
}

# Multi-worker note (Wave B): env BAAS_WORKERS consumed by run_baas_server when supported
$healthUrl = "http://${BindHost}:${Port}/health"
$readyUrl = "http://${BindHost}:${Port}/health/ready"
$ok = $false
for ($i = 0; $i -lt 36; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ok) { throw "health not ready: $healthUrl" }

Write-Host ""
Write-Host "=== BaaS ready ===" -ForegroundColor Green
Write-Host "Health:    $healthUrl"
Write-Host "Ready:     $readyUrl"
Write-Host "Admin:     http://${BindHost}:${Port}/admin/baas"
Write-Host "Login:     http://${BindHost}:${Port}/login"
Write-Host "Bootstrap: http://${BindHost}:${Port}/api/public/client-bootstrap"
Write-Host "GM:        open project → BaaS 运维 → GM"
Write-Host "Workers:   $Workers  Redis: $($WithRedis.IsPresent)  Postgres: $($UsePostgres.IsPresent)"
