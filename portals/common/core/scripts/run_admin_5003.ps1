$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:APK_PORT='5003'
$env:APK_HOST='127.0.0.1'
$env:APP_PORTAL_MODE='admin'
& (Join-Path $root 'venv\Scripts\python.exe') -u -m waitress --listen=127.0.0.1:5003 admin_wsgi:app
