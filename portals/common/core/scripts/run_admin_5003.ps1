$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$port = 5003
$env:APK_PORT = "$port"
$env:APK_HOST = '127.0.0.1'
$env:APP_PORTAL_MODE = 'admin'
if (-not $env:UNITY_PROJECT_PATH -and (Test-Path 'E:\maclient')) {
    $env:UNITY_PROJECT_PATH = 'E:\maclient'
    $env:MACLIENT_ROOT = 'E:\maclient'
}

$lib = Join-Path $PSScriptRoot 'portal5003_lib.ps1'
if (-not (Test-Path $lib)) {
    throw "Missing portal5003_lib.ps1: $lib"
}
. $lib

# Always clean stale duplicate listeners before binding (manual waitress starts included).
$existing = @(Get-Portal5003ListenerPids -Port $port)
if ($existing.Count -gt 0) {
    Write-Host "[run_admin_5003] cleaning $($existing.Count) existing listener(s) on 127.0.0.1:$port"
    Stop-Portal5003Listeners -Port $port | Out-Null
}

$python = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    & py -3 -u -m waitress --listen=127.0.0.1:$port app_new:app
    exit $LASTEXITCODE
}
& $python -u -m waitress --listen=127.0.0.1:$port app_new:app
