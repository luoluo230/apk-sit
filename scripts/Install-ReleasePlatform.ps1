#Requires -Version 5.1
<#
.SYNOPSIS
  Install release platform components for 5-node topology.

.PARAMETER Role
  control | build-android | build-wxminigame

.EXAMPLE
  powershell -File scripts\Install-ReleasePlatform.ps1 -Role control
  powershell -File scripts\Install-ReleasePlatform.ps1 -Role build-android -JenkinsMasterUrl http://127.0.0.1:8082
#>
param(
    [ValidateSet("control", "build-android", "build-wxminigame")]
    [string]$Role = "control",
    [string]$ApkSiteRoot = "",
    [string]$JenkinsMasterUrl = "http://127.0.0.1:8082",
    [string]$UnityVersion = "",
    [string]$PortalBaseUrl = "http://127.0.0.1:5003",
    [string]$NodeId = "",
    [switch]$SkipAgent
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
}
$core = Join-Path $ApkSiteRoot "portals\common\core"

function Write-Step([string]$msg) {
    Write-Host ("[install] {0}" -f $msg) -ForegroundColor Cyan
}

function Test-Command([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Send-BuildNodeHeartbeat {
    param(
        [string]$RoleName,
        [hashtable]$Extra = @{}
    )
    $payload = @{
        role = $RoleName
        node_id = $(if ($NodeId) { $NodeId } else { "$RoleName-$env:COMPUTERNAME" })
        hostname = $env:COMPUTERNAME
        agent_name = $env:COMPUTERNAME
        os = "windows"
        jenkins_master_url = $JenkinsMasterUrl
        unity_version = $UnityVersion
    }
    foreach ($k in $Extra.Keys) { $payload[$k] = $Extra[$k] }
    $json = $payload | ConvertTo-Json -Compress
    $secret = $env:BUILD_NODE_WEBHOOK_SECRET
    if (-not $secret) { $secret = $env:JENKINS_BUILD_WEBHOOK_SECRET }
    if (-not $secret) {
        Write-Host "[install] skip heartbeat (BUILD_NODE_WEBHOOK_SECRET not set)" -ForegroundColor Yellow
        return
    }
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = [Text.Encoding]::UTF8.GetBytes($secret)
    $hash = ($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($json)) | ForEach-Object { $_.ToString("x2") }) -join ""
    try {
        Invoke-RestMethod -Uri "$PortalBaseUrl/api/internal/build-nodes/heartbeat" `
            -Method POST -Body $json -ContentType "application/json; charset=utf-8" `
            -Headers @{ "X-Build-Node-Signature" = "sha256=$hash" } -TimeoutSec 10 | Out-Null
        Write-Step "heartbeat OK role=$RoleName"
    }
    catch {
        Write-Host "[install] heartbeat failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Step "Install-ReleasePlatform role=$Role root=$ApkSiteRoot"

# --- common deps ---
if (-not (Test-Command py)) {
    Write-Host "[install] WARN: Python (py) not found" -ForegroundColor Yellow
}
if (-not (Test-Command java)) {
    Write-Host "[install] WARN: Java not found (Jenkins needs Java)" -ForegroundColor Yellow
}
if (-not (Test-Command git)) {
    Write-Host "[install] WARN: Git not found" -ForegroundColor Yellow
}

switch ($Role) {
    "control" {
        Write-Step "Installing control plane (Portal + optional Jenkins Master)"
        $venvPy = Join-Path $core "venv\Scripts\python.exe"
        if (-not (Test-Path $venvPy)) {
            Write-Step "Creating Python venv"
            Push-Location $core
            & py -3 -m venv venv
            & $venvPy -m pip install -r requirements.txt
            Pop-Location
        }
        Write-Step "Control plane ready. Start Portal:"
        Write-Host "  powershell -File portals\common\core\scripts\run_admin_5003.ps1"
        Write-Step "Optional dev stack:"
        Write-Host "  powershell -File scripts\Start-DevStack.ps1"
    }
    "build-android" {
        Write-Step "Android build node (label=build-android)"
        if (-not $SkipAgent) {
            & powershell -ExecutionPolicy Bypass -File (Join-Path $scriptRoot "jenkins_agent_bootstrap.ps1") `
                -Role build-android -JenkinsMasterUrl $JenkinsMasterUrl -NodeName "android-$env:COMPUTERNAME"
        }
        Send-BuildNodeHeartbeat -RoleName "build-android"
    }
    "build-wxminigame" {
        Write-Step "WeChat minigame build node (label=build-wxminigame)"
        Write-Step "Ensure Unity WebGL module + WX-WASM-SDK-V2 + WeChat DevTools Stable are installed"
        if (-not $SkipAgent) {
            & powershell -ExecutionPolicy Bypass -File (Join-Path $scriptRoot "jenkins_agent_bootstrap.ps1") `
                -Role build-wxminigame -JenkinsMasterUrl $JenkinsMasterUrl -NodeName "wx-$env:COMPUTERNAME"
        }
        Send-BuildNodeHeartbeat -RoleName "build-wxminigame"
    }
}

Write-Host "=== Install-ReleasePlatform DONE ($Role) ===" -ForegroundColor Green
