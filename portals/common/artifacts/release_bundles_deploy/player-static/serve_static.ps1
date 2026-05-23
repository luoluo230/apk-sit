param(
    [int]$Port=8080,
    [switch]$CheckOnly,
    [bool]$InstallPythonIfMissing=$true
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Find-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source, @()) }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, @('-3')) }
    return $null
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $paths = @()
    if ($machinePath) { $paths += $machinePath }
    if ($userPath) { $paths += $userPath }
    if ($paths.Count -gt 0) {
        $env:Path = ($paths -join ';')
    }
}

function Install-Python {
    if (-not $InstallPythonIfMissing) {
        throw "Python 3.10+ is required. Install Python manually or pass -InstallPythonIfMissing `$true."
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python is missing and winget is unavailable. Install Python 3.10+ manually."
    }
    Write-Host "[STEP] Installing Python 3.12 via winget" -ForegroundColor Cyan
    & $winget.Source install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Python."
    }
    Refresh-Path
}

function Find-Python {
    $info = Find-PythonCommand
    if ($info) { return $info }
    Install-Python
    $info = Find-PythonCommand
    if ($info) { return $info }
    throw "Python install completed, but python command still unavailable. Reopen terminal and retry."
}

$www = Join-Path $PSScriptRoot 'www'
if (!(Test-Path (Join-Path $www 'index.html'))) {
    throw "Missing www/index.html. Rebuild player-static bundle first."
}

$pyInfo = Find-Python
$pyCmd = $pyInfo[0]
$pyArgs = $pyInfo[1]
& $pyCmd @pyArgs --version
if ($LASTEXITCODE -ne 0) {
    throw "Python is not available."
}

$ossutil = Get-Command ossutil -ErrorAction SilentlyContinue
if ($ossutil) {
    Write-Host ("[OK] ossutil detected: {0}" -f $ossutil.Source) -ForegroundColor Green
} else {
    Write-Host "[INFO] ossutil not found (safe to ignore for local preview)." -ForegroundColor Yellow
}

if ($CheckOnly) {
    Write-Host "[DONE] Static bundle environment check passed (CheckOnly)." -ForegroundColor Green
    exit 0
}

Write-Host ("[INFO] Serving static site at http://127.0.0.1:{0}" -f $Port) -ForegroundColor Yellow
& $pyCmd @pyArgs -m http.server $Port --directory $www
