# Start-AgentMonitors.ps1
# 为每个 game-server 节点启动一个 agent 监控黑窗口

$ErrorActionPreference = "Continue"
$python = "E:\web\apk-site\venv\Scripts\python.exe"
$script = "E:\web\apk-site\portals\common\core\scripts\agent_monitor.py"
$opsUrl = "http://127.0.0.1:5504"
$opsKey = "ops-read-key-2026"

if (-not (Test-Path $python)) {
    Write-Host "[ERROR] Python not found: $python"
    exit 1
}
if (-not (Test-Path $script)) {
    Write-Host "[ERROR] Script not found: $script"
    exit 1
}

Write-Host "============================================"
Write-Host "  MA Agent Monitors - Multi-Console"
Write-Host "  每个节点一个监控黑窗口"
Write-Host "============================================"
Write-Host ""

# agent_id, probe_host, probe_port, ops_url, ops_key
$agents = @(
    @("gateway-cn-1",       "127.0.0.1", "15050"),
    @("auth-cn-1",          "127.0.0.1", "0"),       # 内部服务，无独立端口
    @("game-cn-1",          "127.0.0.1", "0"),       # 内部服务，无独立端口
    @("cross-cn-1",         "127.0.0.1", "0"),       # 内部服务，无独立端口
    @("ops-cn-1",           "127.0.0.1", "5504"),
    @("redis-cn-1",         "127.0.0.1", "6379"),
    @("mongo-cn-1",         "127.0.0.1", "27017"),
    @("tcp-cn-1",           "127.0.0.1", "5601"),
    @("kcp-cn-1",           "127.0.0.1", "5602"),
    @("http-transport-cn-1","127.0.0.1", "15603")
)

foreach ($a in $agents) {
    $id = $a[0]
    $probeHost = $a[1]
    $port = $a[2]
    $title = "Agent - $id"
    
    Start-Process -FilePath $python -ArgumentList $script, $id, $probeHost, $port, $opsUrl, $opsKey -WorkingDirectory (Split-Path $script -Parent)
    Write-Host "  $id launched"
    Start-Sleep -Milliseconds 500
}

Write-Host ""
Write-Host "============================================"
Write-Host "  All $($agents.Count) agent monitors launched!"
Write-Host "============================================"
