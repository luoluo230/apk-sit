#Requires -Version 5.1
<#
.SYNOPSIS
  服务器+客户端全量联调：拉起 GameServer 黑窗口 → 跑 Portal/BaaS/业务冒烟 → 结果写日志。
#>
param(
    [string]$PortalBase = "http://127.0.0.1:5003",
    [string]$MaclientRepo = "E:\maclient",
    [string]$ApkSiteRoot = "E:\web\apk-site",
    [switch]$SkipServerStart
)

$ErrorActionPreference = "Continue"
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $ApkSiteRoot "docs\qa"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "full_client_server_integration_$ts.log"

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log "=== 全量联调开始 ==="
Log "portal=$PortalBase"
Log "maclient=$MaclientRepo"
Log "log=$logFile"

$unityClient = Join-Path $MaclientRepo "Client"
$serverRoot = Join-Path $MaclientRepo "Server"
$core = Join-Path $ApkSiteRoot "portals\common\core"
$env:MACLIENT_ROOT = $unityClient
$env:UNITY_PROJECT_PATH = $unityClient
$env:PORTAL_BASE = $PortalBase
$env:PORTAL_BASE_URL = $PortalBase

# 1) Portal health
try {
    $h = Invoke-WebRequest -Uri ($PortalBase.TrimEnd('/') + "/health") -UseBasicParsing -TimeoutSec 5
    Log "Portal health HTTP $($h.StatusCode)"
} catch {
    Log "FAIL Portal 不可达: $_"
    exit 2
}

# 2) Start GameServer multi-console (visible black windows)
if (-not $SkipServerStart) {
    $launcher = Join-Path $serverRoot "scripts\Start-GameServer-MultiConsole.ps1"
    Log "启动 GameServer 多黑窗口: $launcher"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $launcher
    if ($LASTEXITCODE -ne 0) {
        Log "WARN MultiConsole exit=$LASTEXITCODE — 尝试单进程可见窗口 --all"
        $startOne = Join-Path $serverRoot "scripts\Start-GameServer.ps1"
        # Override: start visible (patch via Start-Process after build)
        & powershell -NoProfile -ExecutionPolicy Bypass -File $startOne -SkipInstall
    }
    Log "等待 Gateway / Ops 就绪..."
    $deadline = (Get-Date).AddSeconds(90)
    $gw = $false; $ops = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $c = New-Object Net.Sockets.TcpClient
            $iar = $c.BeginConnect("127.0.0.1", 15050, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(500)) { try { $c.EndConnect($iar); $gw = $true } catch {} }
            $c.Close()
        } catch {}
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:5504/ops/ready" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -lt 500) { $ops = $true }
        } catch {}
        if ($gw -and $ops) { break }
        Start-Sleep -Seconds 2
    }
    Log "gateway:15050 open=$gw  ops:5504 ready=$ops"
}

# 3) API / business batteries
$results = @()
function Run-Step([string]$Name, [scriptblock]$Block) {
    Log ">> STEP $Name"
    try {
        & $Block
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
        $ok = ($code -eq 0)
        Log "<< STEP $Name exit=$code ok=$ok"
        $script:results += [pscustomobject]@{ name = $Name; ok = $ok; exit_code = $code }
    } catch {
        Log "<< STEP $Name EXCEPTION $_"
        $script:results += [pscustomobject]@{ name = $Name; ok = $false; error = "$_" }
    }
}

Set-Location $core

Run-Step "startup_gate" {
    py -3 -c @"
import json,urllib.request
u='$PortalBase'.rstrip('/')+'/api/public/startup-gate?project_id=GomeKu&env_key=development&channel=wechat&platform=android'
print(urllib.request.urlopen(u,timeout=10).read().decode())
"@
}

Run-Step "runtime_bootstrap" {
    py -3 -c @"
import json,urllib.request,sys
sys.path.insert(0,r'$core')
from config import load_dotenv; load_dotenv()
from models.data import projects_db
p=projects_db.get('GomeKu') or {}
gid=p.get('game_id') or ''; gkey=p.get('game_key') or ''
from urllib.parse import urlencode
q=urlencode(dict(game_id=gid,game_key=gkey,env_key='development',channel='wechat',platform='android',version_name='1.0.0',version_code='21'))
u='$PortalBase'.rstrip('/')+'/api/public/runtime-bootstrap?'+q
body=json.loads(urllib.request.urlopen(u,timeout=15).read().decode())
print(json.dumps({k:body.get(k) for k in ('ok','project_id','scope_id','active_bundle_id','channel_id','env_key')},ensure_ascii=False))
raise SystemExit(0 if body.get('ok') else 1)
"@
}

Run-Step "runtime_domain_gate" {
    $env:RUNTIME_DOMAIN_UNITY = "0"
    $env:HOTUPDATE_CONFIG_ASSET = (Join-Path $unityClient "Assets\Content\Resources\HotUpdateConfig.asset")
    py -3 (Join-Path $core "scripts\runtime_hotupdate_domain_gate.py")
}

Run-Step "baas_full_integration" {
    py -3 (Join-Path $core "scripts\run_baas_full_integration_e2e.py") --no-start-server --portal $PortalBase
}

Run-Step "transport_login_matrix" {
    py -3 (Join-Path $core "scripts\transport_login_matrix.py")
}

Run-Step "full_stack_integration" {
    $env:MACLIENT_ROOT = $MaclientRepo
    py -3 (Join-Path $core "scripts\run_full_stack_integration_e2e.py") --portal $PortalBase
}

$fail = @($results | Where-Object { -not $_.ok }).Count
$summary = [ordered]@{
    started = $ts
    log = $logFile
    portal = $PortalBase
    gateway_open = $gw
    ops_ready = $ops
    steps = $results
    failed = $fail
    verdict = $(if ($fail -eq 0) { "PASS" } else { "FAIL" })
}
$summaryPath = Join-Path $logDir "full_client_server_integration_$ts.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath -Encoding UTF8
Log "=== 联调结束 verdict=$($summary.verdict) failed=$fail ==="
Log "summary=$summaryPath"
Write-Host ""
Write-Host ($summary | ConvertTo-Json -Depth 6)
exit $(if ($fail -eq 0) { 0 } else { 1 })
