param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)]
    [ValidateSet('admin', 'player', 'forum')]
    [string]$Mode,
    [int]$AppPort
)

$ErrorActionPreference = 'Stop'
Set-Location $AppDir

function Get-PythonLaunchSpec {
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
        return @{
            FilePath = $candidates[0]
            ArgumentPrefix = @()
        }
    }

    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pyLauncher) {
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    }
    if ($pyLauncher -and $pyLauncher.Source) {
        return @{
            FilePath = $pyLauncher.Source
            ArgumentPrefix = @('-3')
        }
    }

    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    }
    if ($pythonCmd -and $pythonCmd.Source) {
        return @{
            FilePath = $pythonCmd.Source
            ArgumentPrefix = @()
        }
    }

    throw "Python executable not found. Checked venv, C:\python, LocalAppData Python installs, py.exe, and PATH."
}

$pythonLaunch = Get-PythonLaunchSpec

$env:APK_PORT = "$AppPort"
$env:APK_HOST = '0.0.0.0'
$env:APP_PORTAL_MODE = $Mode
if ($Mode -eq 'player') {
    $env:ENABLE_DOWNLOAD_FILE_SERVICE = 'false'
    $env:ENABLE_BACKGROUND_SCHEDULER = 'false'
}
if ($Mode -eq 'forum') {
    $env:ENABLE_DOWNLOAD_FILE_SERVICE = 'false'
    $env:ENABLE_BACKGROUND_SCHEDULER = 'false'
}

$logDir = Join-Path $AppDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "$Mode-portal.log"
$errPath = Join-Path $logDir "$Mode-portal.err.log"

$arguments = @()
$arguments += $pythonLaunch.ArgumentPrefix
$arguments += @('-u', '-m', 'waitress', "--listen=0.0.0.0:$AppPort", "$($Mode)_wsgi:app")

& $pythonLaunch.FilePath @arguments 1>> $logPath 2>> $errPath
exit $LASTEXITCODE
