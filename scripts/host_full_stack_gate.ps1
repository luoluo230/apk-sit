#Requires -Version 5.1
<#
.SYNOPSIS
  Wave4 exit when Docker unavailable: validate host stack matches compose intent.
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [string]$GameServerRoot = "E:\maclient\game-server"
)

$ErrorActionPreference = "Stop"

function Test-Tcp($HostName, $Port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(2000)) { $c.Close(); return $false }
        $c.EndConnect($iar); $c.Close(); return $true
    } catch { return $false }
}

$checks = @(
    @{ name = "redis"; ok = (Test-Tcp "127.0.0.1" 6379) },
    @{ name = "mongo"; ok = (Test-Tcp "127.0.0.1" 27017) },
    @{ name = "apk-site"; ok = $false },
    @{ name = "gateway"; ok = (Test-Tcp "127.0.0.1" 15050) }
)
try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 5
    $checks[2].ok = ($r.StatusCode -eq 200)
} catch {}

$fail = @($checks | Where-Object { -not $_.ok })
foreach ($c in $checks) {
    $color = if ($c.ok) { "Green" } else { "Red" }
    Write-Host ("[{0}] {1}" -f $(if ($c.ok) { "OK" } else { "FAIL" }), $c.name) -ForegroundColor $color
}

if ($fail.Count -gt 0) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "Hint: run docker compose -f docker-compose.dev.yml up -d" -ForegroundColor Yellow
    } else {
        Write-Host "Docker not installed; host stack gate validates equivalent ports." -ForegroundColor Yellow
        & powershell -ExecutionPolicy Bypass -File (Join-Path (Split-Path $PSScriptRoot -Parent) "tools\start_release_stack.ps1") -SkipDocker
    }
    if (@($checks | Where-Object { -not $_.ok }).Count -gt 0) { exit 1 }
}
Write-Host "HOST FULL STACK GATE PASSED"
exit 0
