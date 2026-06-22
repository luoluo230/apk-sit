param(
    [string]$ComposeFile = (Join-Path $PSScriptRoot "..\docker-compose.dev.yml"),
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [int]$HealthTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

function Test-DockerAvailable {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return $false
    }
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Wait-Health([string]$Url, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    throw "Health check timed out: $Url"
}

if (-not (Test-DockerAvailable)) {
    if ($env:CLOSURE_MODE -eq "1") {
        Write-Host "FAIL: docker unavailable (CLOSURE_MODE)" -ForegroundColor Red
        exit 1
    }
    Write-Host "SKIP: docker unavailable (docker CLI missing or daemon not running)." -ForegroundColor Yellow
    exit 0
}

$ComposeFile = (Resolve-Path $ComposeFile).Path
$ApkCore = Join-Path $PSScriptRoot "..\portals\common\core" | Resolve-Path
$stackUp = $false

try {
    Write-Host "=== docker compose up ===" -ForegroundColor Cyan
    docker compose -f $ComposeFile up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit code $LASTEXITCODE" }
    $stackUp = $true

    Write-Host "=== health check ===" -ForegroundColor Cyan
    Wait-Health -Url "$BaseUrl/health" -TimeoutSec $HealthTimeoutSec
    Write-Host "health OK"

    Write-Host "=== smoke_check ===" -ForegroundColor Cyan
    Set-Location $ApkCore
    py -3 scripts\smoke_check.py $BaseUrl
    if ($LASTEXITCODE -ne 0) { throw "smoke_check failed with exit code $LASTEXITCODE" }

    Write-Host "=== commercial_startup_sequence_gate ===" -ForegroundColor Cyan
    $env:RELEASE_GATE_BASE_URL = $BaseUrl
    py -3 scripts\commercial_startup_sequence_gate.py
    if ($LASTEXITCODE -ne 0) { throw "commercial_startup_sequence_gate failed with exit code $LASTEXITCODE" }

    Write-Host "docker compose smoke gate PASS" -ForegroundColor Green
    exit 0
} finally {
    if ($stackUp) {
        Write-Host "=== docker compose down ===" -ForegroundColor Cyan
        docker compose -f $ComposeFile down
    }
}
