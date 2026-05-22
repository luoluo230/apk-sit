param(
    [string]$AppDir = "",
    [Parameter(Mandatory = $true)]
    [ValidateSet('admin', 'player', 'forum')]
    [string]$Mode,
    [int]$AppPort
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($AppDir)) {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $AppDir = Split-Path -Parent $PSScriptRoot
    } elseif ($MyInvocation.MyCommand.Path) {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        $AppDir = Split-Path -Parent $scriptDir
    } else {
        throw "Unable to resolve AppDir from script context."
    }
}
Set-Location $AppDir

function Test-PythonExecutable {
    param([string]$ExePath)
    if ([string]::IsNullOrWhiteSpace($ExePath) -or -not (Test-Path $ExePath)) { return $false }
    try {
        $output = & $ExePath --version 2>&1
        return ($LASTEXITCODE -eq 0 -and ($output -match 'Python'))
    } catch {
        return $false
    }
}

function Get-PythonLaunchSpec {
    $venvPython = Join-Path $AppDir 'venv\Scripts\python.exe'
    $candidates = @(
        @{ FilePath = $venvPython; Prefix = @() },
        @{ FilePath = 'C:\python\python.exe'; Prefix = @() },
        @{ FilePath = (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'); Prefix = @() },
        @{ FilePath = (Join-Path $env:LocalAppData 'Programs\Python\Python311\python.exe'); Prefix = @() },
        @{ FilePath = (Join-Path $env:LocalAppData 'Programs\Python\Python310\python.exe'); Prefix = @() },
        @{ FilePath = (Join-Path $env:LocalAppData 'Programs\Python\Python39\python.exe'); Prefix = @() }
    )

    foreach ($item in $candidates) {
        if (Test-PythonExecutable -ExePath $item.FilePath) {
            return @{ FilePath = $item.FilePath; ArgumentPrefix = $item.Prefix }
        }
    }

    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pyLauncher) { $pyLauncher = Get-Command py -ErrorAction SilentlyContinue }
    if ($pyLauncher -and $pyLauncher.Source) {
        try {
            $out = & $pyLauncher.Source -3 --version 2>&1
            if ($LASTEXITCODE -eq 0 -and ($out -match 'Python')) {
                return @{ FilePath = $pyLauncher.Source; ArgumentPrefix = @('-3') }
            }
        } catch {}
    }

    throw "Python executable not found or unusable. venv may be broken; install Python and recreate venv."
}

$pythonLaunch = Get-PythonLaunchSpec

$env:APK_PORT = "$AppPort"
$env:APK_HOST = '0.0.0.0'
$env:APP_PORTAL_MODE = $Mode
if ($Mode -in @('player','forum')) {
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

"[$(Get-Date -Format s)] mode=$Mode port=$AppPort python=$($pythonLaunch.FilePath) args=$($arguments -join ' ')" | Add-Content -Path $logPath -Encoding UTF8
try {
    & $pythonLaunch.FilePath @arguments 1>> $logPath 2>> $errPath
    exit $LASTEXITCODE
} catch {
    $_.Exception.Message | Add-Content -Path $errPath -Encoding UTF8
    throw
}
