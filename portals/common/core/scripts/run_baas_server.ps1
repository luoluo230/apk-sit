param(
    [int]$Port = 5004,
    [string]$BindHost = "127.0.0.1"
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:BAAS_STANDALONE = "1"
$env:PORTAL_SERVER_FRAMEWORKS = "baas"
$env:BAAS_PORT = "$Port"
$env:BAAS_HOST = $BindHost
$env:APP_PORTAL_MODE = "admin"

$python = Join-Path $root "venv\Scripts\python.exe"
$listen = "${BindHost}:$Port"
if (Test-Path $python) {
    & $python -u -m waitress --listen=$listen app_baas:app
    exit $LASTEXITCODE
}
& py -3 -u -m waitress --listen=$listen app_baas:app
