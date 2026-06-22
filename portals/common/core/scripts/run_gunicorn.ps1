param(
    [string]$AppDir = "",
    [ValidateSet('admin', 'player', 'forum')]
    [string]$Mode = 'admin',
    [int]$AppPort = 5003,
    [int]$Workers = 4,
    [string]$BindHost = '0.0.0.0',
    [string]$RedisUrl = 'redis://127.0.0.1:6379/0'
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($AppDir)) {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $AppDir = Split-Path -Parent $PSScriptRoot
    } else {
        throw 'Unable to resolve AppDir.'
    }
}

Set-Location $AppDir
$RootDir = (Resolve-Path (Join-Path $AppDir '..\..\..')).Path
$venvPython = Join-Path $RootDir 'venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }

$env:PORTAL_MODE = $Mode
$env:REDIS_URL = $RedisUrl
$env:SESSION_TYPE = 'redis'
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = 'dev-only-change-me'
}

Write-Host "[gunicorn] mode=$Mode port=$AppPort workers=$Workers redis=$RedisUrl"
& $python -m gunicorn `
    -w $Workers `
    -b "${BindHost}:${AppPort}" `
    --timeout 120 `
    "app_new:create_app()"

exit $LASTEXITCODE
