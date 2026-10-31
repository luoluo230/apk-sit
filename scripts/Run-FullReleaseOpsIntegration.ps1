#Requires -Version 5.1
<#
.SYNOPSIS
  Web + 客户端 + 服务器全流程：运维面 → 同步发版 → Web 部署服务器 → 持续联调。

.DESCRIPTION
  1) 拉起 Portal :5003
  2) 拉起 GameServer MultiConsole（独立黑窗口，便于盯运维/联调日志）
  3) 跑 run_full_release_ops_integration_e2e.py
     - 平台运维 gate
     - Server artifact/release/deploy（Agent）
     - 客户端 Portal 发版链路（Jenkins 可选；不可用会在报告中标明）
     - startup-gate + 热更三域
     - 双端业务 + 长挂心跳

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Run-FullReleaseOpsIntegration.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Run-FullReleaseOpsIntegration.ps1 -HoldSec 180
  powershell -ExecutionPolicy Bypass -File scripts\Run-FullReleaseOpsIntegration.ps1 -RequireJenkins
#>
param(
    [string]$PortalBaseUrl = "http://127.0.0.1:5003",
    [string]$MaclientRoot = "E:\maclient",
    [int]$HoldSec = 180,
    [int]$HeartbeatInterval = 5,
    [switch]$RequireJenkins,
    [switch]$SkipStartInfra,
    [switch]$SkipServerDeploy,
    [switch]$SkipLifecycle
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Core = Join-Path $Root "portals\common\core"
$Multi = Join-Path $MaclientRoot "Server\scripts\Start-GameServer-MultiConsole.ps1"

function Wait-Http([string]$Url, [int]$Sec = 90) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

function Wait-Tcp([string]$HostName, [int]$Port, [int]$Sec = 90) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $iar = $c.BeginConnect($HostName, $Port, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(1000)) {
                try { $c.EndConnect($iar); $c.Close(); return $true } catch {}
            }
            $c.Close()
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

Write-Host "======== 全流程：运维 / 发版 / 部署 / 联调 ========" -ForegroundColor Cyan
Write-Host "Portal=$PortalBaseUrl HoldSec=$HoldSec RequireJenkins=$RequireJenkins"

if (-not $SkipStartInfra) {
    Write-Host "[1/3] Start Portal :5003 ..." -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\Start-Portal5003.ps1") -Background
    if (-not (Wait-Http "$PortalBaseUrl/health" 120)) {
        throw "Portal health not ready: $PortalBaseUrl/health"
    }
    Write-Host "Portal ready" -ForegroundColor Green

    Write-Host "[2/3] Start GameServer MultiConsole (black windows) ..." -ForegroundColor Yellow
    if (-not (Test-Path $Multi)) { throw "MultiConsole missing: $Multi" }
    # Stop previous nodes for clean deploy/联调
    Get-Process GameServer.GameServerApp -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass",
        "-File", $Multi, "-SkipBuild"
    ) -WindowStyle Normal
    if (-not (Wait-Tcp "127.0.0.1" 15050 150)) {
        throw "Gateway WS :15050 not ready"
    }
    if (-not (Wait-Tcp "127.0.0.1" 5504 90)) {
        Write-Host "WARN: Ops :5504 not open yet — continuing, orchestrator will report" -ForegroundColor Yellow
    }
    Write-Host "GameServer nodes launching (watch black consoles)" -ForegroundColor Green
}

Write-Host "[3/3] Run orchestrator ..." -ForegroundColor Yellow
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:MACLIENT_ROOT = $MaclientRoot
$env:GAME_SERVER_REPO = (Join-Path $MaclientRoot "Server")
$env:AGENT_TOKEN = "ops-write-key-2026"
$env:PORTAL_BASE = $PortalBaseUrl
$env:E2E_HOLD_SEC = "$HoldSec"

$pyArgs = @(
    (Join-Path $Core "scripts\run_full_release_ops_integration_e2e.py"),
    "--portal", $PortalBaseUrl,
    "--project-id", "GomeKu",
    "--hold-sec", "$HoldSec",
    "--heartbeat-interval", "$HeartbeatInterval"
)
if ($RequireJenkins) { $pyArgs += "--require-jenkins" }
if ($SkipServerDeploy) { $pyArgs += "--skip-server-deploy" }
if ($SkipLifecycle) { $pyArgs += "--skip-lifecycle" }

# Visible result window runner
$log = Join-Path $Root ("docs\qa\full_release_ops_integration_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$runner = @"
`$Host.UI.RawUI.WindowTitle = 'MA 全流程：发版+运维部署+联调'
chcp 65001 > `$null
`$env:PYTHONIOENCODING='utf-8'
`$env:PYTHONUTF8='1'
`$env:MACLIENT_ROOT='$MaclientRoot'
`$env:GAME_SERVER_REPO='$(Join-Path $MaclientRoot "Server")'
`$env:AGENT_TOKEN='ops-write-key-2026'
`$env:PORTAL_BASE='$PortalBaseUrl'
`$env:E2E_HOLD_SEC='$HoldSec'
Set-Location '$Core'
Write-Host '请同时盯 GameServer 各节点黑窗口（deploy / Heartbeat / Login）' -ForegroundColor Cyan
py -3 -X utf8 $($pyArgs -join ' ') 2>&1 | Tee-Object -FilePath '$log'
Write-Host ''
Write-Host "日志: $log"
Write-Host '证据: $Root\docs\evidence\full-release-ops-integration-latest.json'
Write-Host '按任意键关闭...'
`$null = `$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
"@
$runnerPath = Join-Path $env:TEMP "ma_full_release_ops_integration.ps1"
Set-Content -Path $runnerPath -Value $runner -Encoding UTF8
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", $runnerPath -WindowStyle Normal

Write-Host "Orchestrator window started." -ForegroundColor Green
Write-Host "Log will be: $log"
Write-Host "Evidence: $($Root)\docs\evidence\full-release-ops-integration-latest.json"
