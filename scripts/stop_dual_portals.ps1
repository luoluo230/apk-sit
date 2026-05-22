param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$pidFile = Join-Path (Join-Path $AppDir 'data') 'portal_pids.json'
$taskFile = Join-Path (Join-Path $AppDir 'data') 'portal_tasks.json'
function Stop-PortalTasks {
    $taskRecords = @()
    if (Test-Path $taskFile) {
        try {
            $taskRecords = Get-Content $taskFile -Raw | ConvertFrom-Json
        } catch {}
    }
    foreach ($item in @($taskRecords)) {
        if ($item.task) {
            try { Stop-ScheduledTask -TaskPath '\' -TaskName $item.task -ErrorAction SilentlyContinue | Out-Null } catch {}
            try { Unregister-ScheduledTask -TaskPath '\' -TaskName $item.task -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
        }
    }
    if (Test-Path $taskFile) {
        Remove-Item $taskFile -Force -ErrorAction SilentlyContinue
    }
}

Stop-PortalTasks
if (-not (Test-Path $pidFile)) {
    Write-Output "No PID file found."
    exit 0
}

try {
    $records = Get-Content $pidFile -Raw | ConvertFrom-Json
} catch {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Output "PID file removed."
    exit 0
}

foreach ($item in @($records)) {
    if ($item.pid) {
        try { Stop-Process -Id ([int]$item.pid) -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
Write-Output "Dual portals stopped."
