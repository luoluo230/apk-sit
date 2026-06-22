#Requires -Version 5.1
<#
.SYNOPSIS
  Start closure stack: docker compose (redis/mongo/apk-site) + GameServer cluster.

.EXAMPLE
  powershell -File tools\start_release_stack.ps1
  powershell -File tools\start_release_stack.ps1 -SkipDocker -SkipGameServer
#>
param(
    [switch]$SkipDocker,
    [switch]$SkipGameServer,
    [switch]$SkipSeed,
    [switch]$AllServers,
    [string]$ApkSiteRoot = "",
    [string]$GameServerRoot = "E:\maclient\game-server",
    [string]$BaseUrl = "http://127.0.0.1:5003"
)

$ErrorActionPreference = "Stop"
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Core = Join-Path $ApkSiteRoot "portals\common\core"
$ComposeFile = Join-Path $ApkSiteRoot "docker-compose.dev.yml"

function Test-Tcp([string]$HostName, [int]$Port, [int]$Ms = 2000) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($Ms)) { $c.Close(); return $false }
        $c.EndConnect($iar); $c.Close(); return $true
    } catch { return $false }
}

function Wait-Http([string]$Url, [int]$Sec = 120) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 3 }
    }
    throw "Health timeout: $Url"
}

Write-Host "=== start_release_stack ===" -ForegroundColor Cyan

if (-not $SkipDocker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        if ($env:CLOSURE_MODE -eq "1") { throw "CLOSURE_MODE: docker CLI required" }
        Write-Warning "docker missing; skipping compose"
    } else {
        Write-Host "[stack] docker compose up -d"
        Push-Location $ApkSiteRoot
        docker compose -f $ComposeFile up -d --build
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
        Pop-Location
        Wait-Http "$BaseUrl/health" 180
        Write-Host "[stack] apk-site healthy at $BaseUrl"
    }
} else {
    Write-Host "[stack] SkipDocker"
}

if (-not $SkipSeed) {
    Write-Host "[stack] seed release gate fixture"
    Push-Location $Core
    py -3 scripts\seed_release_gate_fixture.py
    if ($LASTEXITCODE -ne 0) { throw "seed_release_gate_fixture failed" }
    Pop-Location
}

if (-not $SkipGameServer) {
    $exe = Join-Path $GameServerRoot "game-server\bin\Debug\GameServer.GameServerApp.exe"
    if (-not (Test-Path $exe)) {
        $startGs = Join-Path $GameServerRoot "scripts\Start-GameServer.ps1"
        if (Test-Path $startGs) {
            Write-Host "[stack] building + starting via Start-GameServer.ps1"
            & powershell -ExecutionPolicy Bypass -File $startGs -SkipInstall
        }
    } elseif (Test-Tcp "127.0.0.1" 15050 1500) {
        Write-Host "[stack] gateway :15050 already listening"
    } else {
        $exeDir = Split-Path $exe -Parent
        $serverArg = if ($AllServers) { "--all" } else { "--servers=gateway-cn-1,auth-cn-1,game-cn-1,ops-cn-1" }
        Write-Host "[stack] starting GameServer cluster ($serverArg)"
        Start-Process -FilePath $exe -ArgumentList $serverArg -WorkingDirectory $exeDir | Out-Null
        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline) {
            if (Test-Tcp "127.0.0.1" 15050 1000) { break }
            Start-Sleep -Seconds 2
        }
    }
    if (-not (Test-Tcp "127.0.0.1" 15050 3000)) {
        if ($env:CLOSURE_MODE -eq "1") { throw "gateway :15050 not reachable" }
        Write-Warning "gateway :15050 not reachable"
    } else {
        Write-Host "[stack] gateway ws port OK"
    }
}

Write-Host "=== start_release_stack DONE ===" -ForegroundColor Green
