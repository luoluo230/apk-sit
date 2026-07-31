#Requires -Version 5.1
<#
.SYNOPSIS
  One-command local dev stack: Mongo/Redis + GameServer --all + Portal :5003 + client config sync.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Start-DevStack.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Start-DevStack.ps1 -SkipSeed -SkipBuild
  powershell -ExecutionPolicy Bypass -File scripts\Start-DevStack.ps1 -RestartPortal
#>
param(
    [string]$ApkSiteRoot = "",
    [string]$MaclientRoot = "",
    [string]$GameServerRoot = "",
    [string]$PortalBaseUrl = "http://127.0.0.1:5003",
    [string]$GatewayWs = "ws://127.0.0.1:15050/ws",
    [switch]$SkipInstall,
    [switch]$SkipBuild,
    [switch]$SkipGameServer,
    [switch]$SkipPortal,
    [switch]$SkipSeed,
    [switch]$SkipClientSync,
    [switch]$RestartPortal,
    [switch]$OnboardProject,
    [string]$OnboardPayloadFile = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot([string]$Candidate, [string[]]$Fallbacks) {
    if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path $Candidate)) {
        return (Resolve-Path $Candidate).Path
    }
    foreach ($path in $Fallbacks) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return (Resolve-Path $path).Path
        }
    }
    return ""
}

function Test-Tcp([string]$HostName, [int]$Port, [int]$Ms = 2000) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($Ms)) { $client.Close(); return $false }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    }
    catch { return $false }
}

function Wait-HttpOk([string]$Url, [int]$Sec = 120) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) { return $true }
        }
        catch { Start-Sleep -Seconds 2 }
    }
    return $false
}

function Get-HotUpdateGameCredentials([string]$Root) {
    $asset = Join-Path $Root "Assets\Content\Resources\HotUpdateConfig.asset"
    if (-not (Test-Path $asset)) {
        return @{ GameId = ""; GameKey = ""; Version = "1.0.0"; Channel = "wechat" }
    }
    $text = Get-Content $asset -Raw
    function Read-Field([string]$Name) {
        if ($text -match '(?m)^\s*' + [regex]::Escape($Name) + ':\s*(.+?)\s*$') { return $Matches[1].Trim() }
        return ""
    }
    return @{
        GameId = Read-Field "GameId"
        GameKey = Read-Field "GameKey"
        Version = Read-Field "CurrentClientVersion"
        Channel = Read-Field "Channel"
    }
}

function Write-Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
    $label = if ($Ok) { "OK" } else { "FAIL" }
    $color = if ($Ok) { "Green" } else { "Red" }
    $suffix = if ($Detail) { " - $Detail" } else { "" }
    Write-Host ("[{0}] {1}{2}" -f $label, $Name, $suffix) -ForegroundColor $color
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = Resolve-RepoRoot "" @((Resolve-Path (Join-Path $scriptRoot "..")).Path)
}
if (-not $MaclientRoot) {
    $MaclientRoot = Resolve-RepoRoot "" @($env:MACLIENT_ROOT, $env:UNITY_PROJECT_PATH, "E:\maclient")
}
if (-not $GameServerRoot) {
    if ($MaclientRoot) {
        $GameServerRoot = Join-Path $MaclientRoot "game-server"
    }
    if (-not (Test-Path $GameServerRoot)) {
        $GameServerRoot = "E:\maclient\game-server"
    }
}

if (-not $ApkSiteRoot) { throw "apk-site root not found" }
if (-not $MaclientRoot) { throw "maclient root not found; set MACLIENT_ROOT" }

$Core = Join-Path $ApkSiteRoot "portals\common\core"
$PortalScript = Join-Path $Core "scripts\run_admin_5003.ps1"
$StartPortalScript = Join-Path $scriptRoot "Start-Portal5003.ps1"
$StopPortalScript = Join-Path $scriptRoot "Stop-Portal5003.ps1"
$PortalLib = Join-Path $Core "scripts\portal5003_lib.ps1"
$SyncScript = Join-Path $scriptRoot "Sync-DevStackClientConfig.ps1"
$StartGameServerScript = Join-Path $GameServerRoot "scripts\Start-GameServer.ps1"
$SeedScript = Join-Path $Core "scripts\seed_release_gate_fixture.py"
$portal = ($(if ($PortalBaseUrl) { $PortalBaseUrl } else { "" })).Trim().TrimEnd("/")

$env:OPS_DEV_UNIFIED_GAMESERVER_ALL = "1"
$env:MACLIENT_ROOT = $MaclientRoot
$env:UNITY_PROJECT_PATH = $MaclientRoot

Write-Host "=== Start-DevStack ===" -ForegroundColor Cyan
Write-Host "[dev-stack] apk-site=$ApkSiteRoot"
Write-Host "[dev-stack] maclient=$MaclientRoot"
Write-Host "[dev-stack] game-server=$GameServerRoot"
Write-Host "[dev-stack] portal=$portal gateway=$GatewayWs"

# --- Dependencies ---
$mongoOk = Test-Tcp "127.0.0.1" 27017
$redisOk = Test-Tcp "127.0.0.1" 6379
Write-Check "mongo:27017" $mongoOk $(if (-not $mongoOk) { "start MongoDB before client login" } else { "" })
Write-Check "redis:6379" $redisOk $(if (-not $redisOk) { "start Redis/Memurai before GameServer" } else { "" })
if (-not $mongoOk -or -not $redisOk) {
    Write-Host "[dev-stack] Hint: game-server Start-GameServer.ps1 can install/start deps via winget (without -SkipInstall)." -ForegroundColor Yellow
}

# --- GameServer ---
if (-not $SkipGameServer) {
    $devstackEnv = Join-Path $ApkSiteRoot ".env.devstack"
    $devstackExample = Join-Path $ApkSiteRoot ".env.devstack.example"
    if (-not (Test-Path $devstackEnv)) {
        if (Test-Path $devstackExample) {
            Copy-Item $devstackExample $devstackEnv
        }
        else {
            Set-Content -Path $devstackEnv -Value "CLUSTER_RELAY_TOKEN=`n" -Encoding UTF8
        }
    }
    Get-Content $devstackEnv | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -gt 0) {
            $k = $line.Substring(0, $eq).Trim()
            $v = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
            if ($k -and -not (Get-Item -Path "env:$k" -ErrorAction SilentlyContinue)) {
                Set-Item -Path "env:$k" -Value $v
            }
        }
    }
    if (-not $env:CLUSTER_RELAY_TOKEN) {
        $bytes = New-Object byte[] 24
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $env:CLUSTER_RELAY_TOKEN = [Convert]::ToBase64String($bytes).TrimEnd('=')
        Add-Content -Path $devstackEnv -Value "CLUSTER_RELAY_TOKEN=$($env:CLUSTER_RELAY_TOKEN)" -Encoding UTF8
        Write-Host "[dev-stack] generated CLUSTER_RELAY_TOKEN in .env.devstack (gitignored)"
    }
    if (Test-Tcp "127.0.0.1" 15050 1500) {
        Write-Host "[dev-stack] gateway :15050 already listening"
    }
    elseif (Test-Path $StartGameServerScript) {
        Write-Host "[dev-stack] starting GameServer via Start-GameServer.ps1"
        $gsArgs = @("-ExecutionPolicy", "Bypass", "-File", $StartGameServerScript)
        if ($SkipInstall) { $gsArgs += "-SkipInstall" }
        if ($SkipBuild) { $gsArgs += "-SkipBuild" }
        & powershell @gsArgs
        if ($LASTEXITCODE -ne 0) { throw "Start-GameServer.ps1 failed exit=$LASTEXITCODE" }
    }
    else {
        throw "Start-GameServer.ps1 not found: $StartGameServerScript"
    }
}
else {
    Write-Host "[dev-stack] SkipGameServer"
}

# --- Portal ---
if (-not $SkipPortal) {
    $healthUrl = "$portal/health"
    $portalOk = $false
    if (Test-Path $PortalLib) {
        . $PortalLib
        $listenerPids = @(Get-Portal5003ListenerPids -Port 5003)
        if ($listenerPids.Count -gt 1) {
            Write-Host "[dev-stack] multiple Portal listeners on :5003 ($($listenerPids -join ', ')) — cleaning" -ForegroundColor Yellow
            if (Test-Path $StopPortalScript) {
                & powershell -NoProfile -ExecutionPolicy Bypass -File $StopPortalScript
            }
            else {
                Stop-Portal5003Listeners -Port 5003 | Out-Null
            }
            $portalOk = $false
        }
        elseif ($listenerPids.Count -eq 1 -and -not $RestartPortal) {
            $portalOk = Wait-HttpOk $healthUrl 3
            if ($portalOk) {
                try {
                    Assert-SinglePortal5003Listener -Port 5003 -BaseUrl $portal | Out-Null
                }
                catch {
                    Write-Host "[dev-stack] Portal health OK but listener check failed: $($_.Exception.Message)" -ForegroundColor Yellow
                    $portalOk = $false
                }
            }
        }
    }
    elseif (-not $RestartPortal) {
        $portalOk = Wait-HttpOk $healthUrl 3
    }
    if ($RestartPortal -and (Test-Path $StopPortalScript)) {
        Write-Host "[dev-stack] RestartPortal — stopping existing Portal :5003"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $StopPortalScript
        $portalOk = $false
    }
    if ($portalOk) {
        Write-Host "[dev-stack] portal already healthy at $portal (single listener)"
    }
    elseif (Test-Path $StartPortalScript) {
        Write-Host "[dev-stack] starting Portal admin on :5003 (single-instance)"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $StartPortalScript -ApkSiteRoot $ApkSiteRoot -Background
        if ($LASTEXITCODE -ne 0) { throw "Start-Portal5003.ps1 failed exit=$LASTEXITCODE" }
        if (-not (Wait-HttpOk $healthUrl 120)) {
            throw "Portal health timeout: $healthUrl"
        }
        Write-Host "[dev-stack] portal healthy"
    }
    elseif (Test-Path $PortalScript) {
        Write-Host "[dev-stack] starting Portal admin on :5003 (background, legacy runner)"
        $portalProc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $PortalScript
        ) -WorkingDirectory $Core -PassThru -WindowStyle Minimized
        Write-Host "[dev-stack] portal pid=$($portalProc.Id)"
        if (-not (Wait-HttpOk $healthUrl 120)) {
            throw "Portal health timeout: $healthUrl"
        }
        Write-Host "[dev-stack] portal healthy"
    }
    else {
        throw "Portal start script not found: $StartPortalScript"
    }
}
else {
    Write-Host "[dev-stack] SkipPortal"
}

# --- Seed published bundle for bootstrap ---
if (-not $SkipSeed) {
    if (Test-Path $SeedScript) {
        Write-Host "[dev-stack] seed release gate fixture"
        Push-Location $Core
        try {
            & py -3 $SeedScript
            if ($LASTEXITCODE -ne 0) { throw "seed_release_gate_fixture failed exit=$LASTEXITCODE" }
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Warning "seed script missing: $SeedScript"
    }
}
else {
    Write-Host "[dev-stack] SkipSeed"
}

# --- Client config sync (P0-1 defaults) ---
if (-not $SkipClientSync) {
    if (-not (Test-Path $SyncScript)) {
        throw "Sync script missing: $SyncScript"
    }
    & powershell -ExecutionPolicy Bypass -File $SyncScript `
        -MaclientRoot $MaclientRoot `
        -PortalBaseUrl $portal `
        -GatewayWs $GatewayWs
    if ($LASTEXITCODE -ne 0) { throw "Sync-DevStackClientConfig failed exit=$LASTEXITCODE" }
}
else {
    Write-Host "[dev-stack] SkipClientSync"
}

# --- Summary ---
$creds = Get-HotUpdateGameCredentials $MaclientRoot
$bootstrapOk = $false
$bootstrapDetail = "skipped"
if ($creds.GameId -and $creds.GameKey) {
    $query = @{
        game_id = $creds.GameId
        game_key = $creds.GameKey
        env_key = "development"
        channel = $(if ($creds.Channel) { $creds.Channel } else { "wechat" })
        platform = "android"
        version_name = $(if ($creds.Version) { $creds.Version } else { "1.0.0" })
    } | ForEach-Object { $_.GetEnumerator() } |
        ForEach-Object { "{0}={1}" -f $_.Key, [uri]::EscapeDataString([string]$_.Value) }
    $bootstrapUrl = "$portal/api/public/runtime-bootstrap?$($query -join '&')"
    try {
        $boot = Invoke-RestMethod -Uri $bootstrapUrl -TimeoutSec 8
        $bootstrapOk = [bool]$boot.ok
        $gw = $boot.network_profile.gateway_ws
        $bootstrapDetail = if ($bootstrapOk) { "gateway_ws=$gw" } else { [string]$boot.error }
    }
    catch {
        $bootstrapDetail = $_.Exception.Message
    }
}

if ($OnboardProject) {
    $payloadPath = $OnboardPayloadFile
    if ([string]::IsNullOrWhiteSpace($payloadPath)) {
        $payloadPath = Join-Path $ApkSiteRoot "tmp\onboard-gomeku.json"
    }
    if (-not (Test-Path $payloadPath)) {
        Write-Warning "Onboard payload not found: $payloadPath"
    }
    else {
        try {
            $body = Get-Content -Raw -Encoding UTF8 $payloadPath
            $onboardUrl = "$portal/api/admin/projects/onboard"
            $resp = Invoke-RestMethod -Uri $onboardUrl -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 30
            Write-Host "Onboard OK: $($resp.data.project_id)" -ForegroundColor Green
        }
        catch {
            Write-Warning "Onboard failed: $($_.Exception.Message)"
        }
    }
}

Write-Host ""
Write-Host "=== Dev Stack Summary ===" -ForegroundColor Cyan
Write-Check "mongo:27017" (Test-Tcp "127.0.0.1" 27017)
Write-Check "redis:6379" (Test-Tcp "127.0.0.1" 6379)
Write-Check "gateway:15050" (Test-Tcp "127.0.0.1" 15050)
Write-Check "ops:5504" (Test-Tcp "127.0.0.1" 5504)
Write-Check "portal:5003" (Wait-HttpOk "$portal/health" 3)
Write-Check "runtime-bootstrap" $bootstrapOk $bootstrapDetail
Write-Host ""
Write-Host "Portal:    $portal  (login: see data/users or admin seed)" -ForegroundColor White
Write-Host "Gateway:   $GatewayWs" -ForegroundColor White
Write-Host "Unity:     open $MaclientRoot and press Play (Profile=Development)" -ForegroundColor White
Write-Host "Resync:    powershell -File scripts\Sync-DevStackClientConfig.ps1" -ForegroundColor White
Write-Host "=== Start-DevStack DONE ===" -ForegroundColor Green

$hardFail = @(
    (Test-Tcp "127.0.0.1" 15050),
    (Wait-HttpOk "$portal/health" 3)
) | Where-Object { -not $_ }
if ($hardFail.Count -gt 0) {
    exit 1
}
