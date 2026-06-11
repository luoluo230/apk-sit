$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:APK_PORT='5003'
$env:APK_HOST='127.0.0.1'
$env:APP_PORTAL_MODE='admin'
$python = Join-Path $root 'venv\\Scripts\\python.exe'
if (-not (Test-Path $python)) {
    & py -3 -u -m waitress --listen=127.0.0.1:5003 app_new:app
    exit $LASTEXITCODE
}
& $python -u -m waitress --listen=127.0.0.1:5003 app_new:app
