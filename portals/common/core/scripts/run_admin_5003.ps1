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

# Avoid stale duplicate listeners (old code without new routes) on the same port.
$pids = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($procId in $pids) {
    if ($procId -and $procId -ne 0) {
        Write-Host "Stopping existing listener on 127.0.0.1:$port (PID $procId)"
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}
if ($pids.Count -gt 0) {
    Start-Sleep -Seconds 1
}

$python = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    & py -3 -u -m waitress --listen=127.0.0.1:$port app_new:app
    exit $LASTEXITCODE
}
& $python -u -m waitress --listen=127.0.0.1:$port app_new:app
