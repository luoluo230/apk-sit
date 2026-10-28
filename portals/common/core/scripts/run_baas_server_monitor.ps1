#Requires -Version 5.1
<#
.SYNOPSIS
  AFK BaaS 健康监控（PowerShell 版，勿用 Python 的 while(True)）。

.EXAMPLE
  cd E:/web/apk-site/portals/common/core
  ./scripts/run_baas_server_monitor.ps1

.EXAMPLE
  ./scripts/run_baas_server_monitor.ps1 -IntervalSec 5 -HealthUrl "http://127.0.0.1:5004/health"
#>
param(
    [string]$HealthUrl = "http://127.0.0.1:5004/health",
    [int]$IntervalSec = 10
)

$coreRoot = Split-Path -Parent $PSScriptRoot
$startHint = Join-Path $coreRoot "scripts\run_baas_server.ps1"

Write-Host "=== AFK BaaS Server Monitor ===" -ForegroundColor Cyan
Write-Host "URL: $HealthUrl"
Write-Host "If you need to START server manually:" -ForegroundColor Yellow
Write-Host " cd $coreRoot"
Write-Host " ./scripts/run_baas_server.ps1"
Write-Host ""

while ($true) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 5
        $ok = $false
        if ($resp -is [bool]) { $ok = $resp }
        elseif ($resp.PSObject.Properties.Name -contains "ok") { $ok = [bool]$resp.ok }
        else { $ok = $true }
        if ($ok) {
            Write-Host "[$stamp] OK  $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
        } else {
            Write-Host "[$stamp] FAIL body=$($resp | ConvertTo-Json -Compress)" -ForegroundColor Red
        }
    } catch {
        Write-Host "[$stamp] FAIL $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "  -> Start: powershell -ExecutionPolicy Bypass -File `"$startHint`"" -ForegroundColor DarkYellow
    }
    Start-Sleep -Seconds $IntervalSec
}
