param(
    [int]$Port = 5004,
    [string]$BindHost = "127.0.0.1"
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$envFile = Join-Path $PSScriptRoot "baas-database.env"
# A caller that selected standalone SQLite must not be silently redirected to
# baas-database.env by this child process. PostgreSQL launchers opt in explicitly.
if (-not $env:DATABASE_URL -and $env:BAAS_USE_DATABASE_ENV -eq "1" -and (Test-Path $envFile)) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) { $val = $val.Substring(1, $val.Length - 2) }
        Set-Item -Path "Env:$key" -Value $val
    }
    if ($env:DATABASE_URL) {
        Write-Host "[baas] DATABASE_URL loaded from baas-database.env" -ForegroundColor DarkGray
    }
}

$env:BAAS_STANDALONE = "1"
$env:PORTAL_SERVER_FRAMEWORKS = "baas"
$env:BAAS_PORT = "$Port"
$env:BAAS_HOST = $BindHost
$env:BAAS_ACCESS_LOG = "1"
$env:BAAS_VERBOSE = "1"
$env:APP_PORTAL_MODE = "admin"

$threads = 4
if ($env:BAAS_WORKERS -match '^\d+$' -and [int]$env:BAAS_WORKERS -gt 0) {
    # Wave B：Windows 用 waitress threads 近似多 worker
    $threads = [Math]::Max(4, [int]$env:BAAS_WORKERS * 4)
}
$python = Join-Path $root "venv\Scripts\python.exe"
$listen = "${BindHost}:$Port"
Write-Host "[baas] waitress listen=$listen threads=$threads"
if (Test-Path $python) {
    & $python -u -m waitress --listen=$listen --threads=$threads app_baas:app
    exit $LASTEXITCODE
}
& py -3 -u -m waitress --listen=$listen --threads=$threads app_baas:app
