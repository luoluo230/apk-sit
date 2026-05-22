param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [int]$AdminPort = 5003,
    [int]$PlayerPort = 5004,
    [switch]$UseScheduledTasks,
    [switch]$StartPlayer
)

$ErrorActionPreference = 'Stop'
Set-Location $AppDir

$logDir = Join-Path $AppDir 'logs'
$dataDir = Join-Path $AppDir 'data'
$pidFile = Join-Path $dataDir 'portal_pids.json'
$taskFile = Join-Path $dataDir 'portal_tasks.json'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

function Test-PythonExecutable {
    param([string]$ExePath)
    if ([string]::IsNullOrWhiteSpace($ExePath) -or -not (Test-Path $ExePath)) { return $false }
    try {
        $out = & $ExePath --version 2>&1
        return ($LASTEXITCODE -eq 0 -and ($out -match 'Python'))
    } catch { return $false }
}

function Get-PythonExecutable {
    $venvPython = Join-Path $AppDir 'venv\Scripts\python.exe'
    $candidates = @(
        $venvPython,
        'C:\python\python.exe',
        (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python310\python.exe'),
        (Join-Path $env:LocalAppData 'Programs\Python\Python39\python.exe')
    )
    foreach($c in $candidates){ if(Test-PythonExecutable -ExePath $c){ return $c } }
    throw "No usable Python found. Please install Python and recreate venv."
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-ExistingPortals {
    $existing = @()
    if (Test-Path $pidFile) {
        try { $existing = Get-Content $pidFile -Raw | ConvertFrom-Json } catch {}
    }
    foreach ($item in @($existing)) {
        if ($item.pid) {
            try { Stop-Process -Id ([int]$item.pid) -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Get-TaskName { param([string]$Mode) return "apk-site-$Mode-portal" }

function Register-PortalTask {
    param([string]$Mode,[int]$Port)
    $taskName = Get-TaskName -Mode $Mode
    $taskPath = '\'
    $runScript = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -AppDir `"$AppDir`" -Mode $Mode -AppPort $Port"
    try { Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $AppDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest -LogonType ServiceAccount
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    return @{ mode=$Mode; port=$Port; task=$taskName; started_at=(Get-Date).ToString('s') }
}

function Start-PortalProcess {
    param([string]$Mode,[int]$Port)
    $runScript = Join-Path $AppDir 'scripts\run_portal_waitress.ps1'
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$runScript,'-AppDir',$AppDir,'-Mode',$Mode,'-AppPort',$Port)
    $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $AppDir -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    $alive = $true
    try { $null = Get-Process -Id $proc.Id -ErrorAction Stop } catch { $alive = $false }
    if(-not $alive){
        $err = Join-Path $logDir "$Mode-portal.err.log"
        $errTail = ''
        if(Test-Path $err){ $errTail = (Get-Content -Path $err -Tail 20 -ErrorAction SilentlyContinue) -join "`n" }
        throw "Portal process exited immediately. mode=$Mode port=$Port. error=$errTail"
    }
    return @{ mode=$Mode; port=$Port; pid=$proc.Id; started_at=(Get-Date).ToString('s') }
}

$records = @()
if ($UseScheduledTasks) {
    if (-not (Test-Admin)) { throw "Scheduled-task mode requires an elevated PowerShell session." }
    $records += Register-PortalTask -Mode 'admin' -Port $AdminPort
    if ($StartPlayer) { $records += Register-PortalTask -Mode 'player' -Port $PlayerPort }
    $records | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $taskFile
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
} else {
    $null = Get-PythonExecutable
    Stop-ExistingPortals
    $records += Start-PortalProcess -Mode 'admin' -Port $AdminPort
    if ($StartPlayer) { $records += Start-PortalProcess -Mode 'player' -Port $PlayerPort }
    $records | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 $pidFile
    if (Test-Path $taskFile) { Remove-Item $taskFile -Force -ErrorAction SilentlyContinue }
}

Write-Output "Admin portal:  http://127.0.0.1:$AdminPort"
if($StartPlayer){ Write-Output "Player portal: http://127.0.0.1:$PlayerPort" } else { Write-Output "Player portal: skipped (single intranet mode)" }
if ($UseScheduledTasks) { Write-Output "Task file: $taskFile" } else { Write-Output "PID file: $pidFile" }


