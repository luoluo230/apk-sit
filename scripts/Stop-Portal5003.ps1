#Requires -Version 5.1
<#
.SYNOPSIS
  Stop every process listening on Portal port 5003 (and related orphaned waitress workers).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Stop-Portal5003.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Stop-Portal5003.ps1 -Port 5003 -Quiet
#>
param(
    [int]$Port = 5003,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$lib = Join-Path $repoRoot "portals\common\core\scripts\portal5003_lib.ps1"
if (-not (Test-Path $lib)) { throw "Missing library: $lib" }
. $lib

$before = @(Get-Portal5003ListenerRows -Port $Port)
if ($before.Count -eq 0 -and -not $Quiet) {
    Write-Host "[Stop-Portal5003] no listeners on :$Port" -ForegroundColor Green
}
else {
    if (-not $Quiet) {
        Write-Host "[Stop-Portal5003] found $($before.Count) listener row(s) on :$Port" -ForegroundColor Cyan
        foreach ($row in $before) {
            $info = Get-Portal5003ProcessInfo -ProcessId $row.OwningProcess
            $cmd = if ($info) { $info.CommandLine } else { "" }
            Write-Host ("  - PID {0} {1} via {2}" -f $row.OwningProcess, $row.LocalAddress, $row.Source)
            if ($cmd) { Write-Host "    $cmd" -ForegroundColor DarkGray }
        }
    }
}

$stopped = @(Stop-Portal5003Listeners -Port $Port -Quiet:$Quiet)
Remove-Portal5003Lock -RepoRoot $repoRoot

$after = @(Get-Portal5003ListenerPids -Port $Port)
if ($after.Count -gt 0) {
    Write-Host "[Stop-Portal5003] FAIL: still listening PIDs: $($after -join ', ')" -ForegroundColor Red
    exit 1
}

if (-not $Quiet) {
    Write-Host ("[Stop-Portal5003] OK stopped {0} process(es)" -f $stopped.Count) -ForegroundColor Green
}
exit 0
