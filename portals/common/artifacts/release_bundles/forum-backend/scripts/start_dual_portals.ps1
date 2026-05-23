param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [int]$AdminPort = 5003,
    [int]$PlayerPort = 5004,
    [switch]$UseScheduledTasks
)

$ErrorActionPreference = 'Stop'
Set-Location $AppDir

$logDir = Join-Path $AppDir 'logs'
$dataDir = Join-Path $AppDir 'data'
$pidFile = Join-Path $dataDir 'portal_pids.json'
$taskFile = Join-Path $dataDir 'portal_tasks.json'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

function Get-PythonExecutable {
    $venvPython = Join-Path $AppDir 'venv\Scripts\python.exe'
    $candidates = @(
        $venvPython,
        'C:\python\python.exe',
        (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python39\python.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) {
        return $candidates[0]
    }

    if (Test-Path $venvPython) {
        return $venvPython
    }
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source) {
        return $pythonCmd.Source
    }
    if ($pyLauncher -and $pyLauncher.Source) {
        return $pyLauncher.Source
    }
    throw "Python executable not found. Checked venv, C:\python, LocalAppData Python installs, py.exe, and PATH."
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-ExistingPortals {
    $existing = @()
    if (Test-Path $pidFile) {
        try {
            $existing = Get-Content $pidFile -Raw | ConvertFrom-Json
        } catch {}
    }
    foreach ($item in @($existing)) {
        if ($item.pid) {
            try { Stop-Process -Id ([int]$item.pid) -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Get-TaskName {
    param(
        [string]$Mode
    )
    return "apk-site-$Mode-portal"
}

function Register-PortalTask {
    param(
        [string]$Mode,
        [int]$Port
    )

    $taskName = Get-TaskName -Mode $Mode
    $taskPath = '\'
    $runScript = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -AppDir `"$AppDir`" -Mode $Mode -AppPort $Port"
    try {
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    } catch {}
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $AppDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest -LogonType ServiceAccount
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    return @{
        mode = $Mode
        port = $Port
        task = $taskName
        started_at = (Get-Date).ToString('s')
    }
}

function Start-PortalProcess {
    param(
        [string]$Mode,
        [int]$Port
    )

    $runScript = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $runScript,
        '-AppDir', $AppDir,
        '-Mode', $Mode,
        '-AppPort', $Port
    )
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $AppDir -WindowStyle Hidden -PassThru
    return @{
        mode = $Mode
        port = $Port
        pid = $proc.Id
        started_at = (Get-Date).ToString('s')
    }
}

$records = @()
if ($UseScheduledTasks) {
    if (-not (Test-Admin)) {
        throw "Scheduled-task mode requires an elevated PowerShell session."
    }
    $records += Register-PortalTask -Mode 'admin' -Port $AdminPort
    $records += Register-PortalTask -Mode 'player' -Port $PlayerPort
    $records | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $taskFile
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
} else {
    $null = Get-PythonExecutable
    Stop-ExistingPortals
    $records += Start-PortalProcess -Mode 'admin' -Port $AdminPort
    $records += Start-PortalProcess -Mode 'player' -Port $PlayerPort
    $records | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $pidFile
    if (Test-Path $taskFile) {
        Remove-Item $taskFile -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "Admin portal:  http://127.0.0.1:$AdminPort"
Write-Output "Player portal: http://127.0.0.1:$PlayerPort"
if ($UseScheduledTasks) {
    Write-Output "Task file: $taskFile"
} else {
    Write-Output "PID file: $pidFile"
}
