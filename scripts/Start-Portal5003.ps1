#Requires -Version 5.1
<#
.SYNOPSIS
  Start exactly one Portal admin instance on 127.0.0.1:5003 (cleans duplicates first).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Start-Portal5003.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Start-Portal5003.ps1 -Background
  powershell -ExecutionPolicy Bypass -File scripts\Start-Portal5003.ps1 -VerifyAgentPull
#>
param(
    [string]$ApkSiteRoot = "",
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [int]$Port = 5003,
    [switch]$Background,
    [switch]$SkipCleanup,
    [switch]$VerifyAgentPull,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ApkSiteRoot) {
    $ApkSiteRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
}
$lib = Join-Path $ApkSiteRoot "portals\common\core\scripts\portal5003_lib.ps1"
$runner = Join-Path $ApkSiteRoot "portals\common\core\scripts\run_admin_5003.ps1"
if (-not (Test-Path $lib)) { throw "Missing library: $lib" }
if (-not (Test-Path $runner)) { throw "Missing runner: $runner" }
. $lib

function Write-Portal5003Msg([string]$Text, [string]$Color = "White") {
    if (-not $Quiet) {
        Write-Host $Text -ForegroundColor $Color
    }
}

if (-not $SkipCleanup) {
    $existing = @(Get-Portal5003ListenerPids -Port $Port)
    if ($existing.Count -gt 0) {
        Write-Portal5003Msg "[Start-Portal5003] cleaning $($existing.Count) existing listener(s) on :$Port" "Yellow"
        Stop-Portal5003Listeners -Port $Port -Quiet:$Quiet | Out-Null
        Remove-Portal5003Lock -RepoRoot $ApkSiteRoot
    }
}

$core = Join-Path $ApkSiteRoot "portals\common\core"
if ($Background) {
    Write-Portal5003Msg "[Start-Portal5003] launching background Portal on :$Port" "Cyan"
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $runner
    ) -WorkingDirectory $core -PassThru -WindowStyle Minimized
    Write-Portal5003Msg "[Start-Portal5003] launcher pid=$($proc.Id)" "DarkGray"
}
else {
    Write-Portal5003Msg "[Start-Portal5003] starting foreground Portal on :$Port (Ctrl+C to stop)" "Cyan"
    Write-Portal5003Msg "[Start-Portal5003] tip: use -Background for DevStack-style detached start" "DarkGray"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $runner
    exit $LASTEXITCODE
}

if (-not (Wait-Portal5003Healthy -BaseUrl $BaseUrl -TimeoutSec 120)) {
    throw "Portal health timeout: $BaseUrl/health"
}

$state = Assert-SinglePortal5003Listener -Port $Port -BaseUrl $BaseUrl
Write-Portal5003Lock -RepoRoot $ApkSiteRoot -ProcessId $state.ProcessId -BaseUrl $BaseUrl -StartedBy "Start-Portal5003.ps1"

if ($VerifyAgentPull) {
    $pull = Test-Portal5003AgentPullReady -BaseUrl $BaseUrl
    if (-not $pull.Ok) {
        throw "Portal agent pull preflight failed: $($pull.Reason)"
    }
    Write-Portal5003Msg "[Start-Portal5003] agent pull preflight OK (jobs=$($pull.Jobs))" "Green"
}

Write-Portal5003Msg ("[Start-Portal5003] OK pid={0} url={1}" -f $state.ProcessId, $BaseUrl) "Green"
exit 0
