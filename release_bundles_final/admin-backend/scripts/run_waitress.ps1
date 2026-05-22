param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [int]$AppPort = 5003
)

$ErrorActionPreference = 'Stop'

Set-Location $AppDir

$waitressExe = Join-Path $AppDir 'venv\Scripts\waitress-serve.exe'
$pythonExe = Join-Path $AppDir 'venv\Scripts\python.exe'

if (Test-Path $waitressExe) {
    & $waitressExe "--listen=0.0.0.0:$AppPort" "app_new:app"
    exit $LASTEXITCODE
}

if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found: $pythonExe"
}

& $pythonExe -m waitress "--listen=0.0.0.0:$AppPort" "app_new:app"
exit $LASTEXITCODE
