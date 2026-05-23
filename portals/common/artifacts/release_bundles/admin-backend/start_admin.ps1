param(
    [int]$Port=5003,
    [switch]$CheckOnly,
    [switch]$SkipInstall,
    [bool]$InstallPythonIfMissing=$true
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "[STEP] $Text" -ForegroundColor Cyan
}

function Find-PythonCommand {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Cmd = $python.Source; Args = @() }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Cmd = $py.Source; Args = @('-3') }
    }
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
    Write-Step "Installing Python 3.12 via winget"
    & $winget.Source install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install Python."
    }
    Refresh-Path
}

function Find-Python {
    $info = Find-PythonCommand
    if ($info) {
        return $info
    }
    Install-Python
    $info = Find-PythonCommand
    if ($info) {
        return $info
    }
    throw "Python install completed, but python command still unavailable. Reopen terminal and retry."
}

function Invoke-RootPython([hashtable]$Info, [string[]]$PyArgs) {
    & $Info.Cmd @($Info.Args) @PyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($PyArgs -join ' ')"
    }
}

Write-Step "Checking Python"
$pyInfo = Find-Python
$versionText = (& $pyInfo.Cmd @($pyInfo.Args) --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query Python version"
}
$match = [regex]::Match($versionText, 'Python\s+(\d+)\.(\d+)\.(\d+)')
if (-not $match.Success) {
    throw "Invalid Python version output: $versionText"
}
$major = [int]$match.Groups[1].Value
$minor = [int]$match.Groups[2].Value
$version = "$($match.Groups[1].Value).$($match.Groups[2].Value).$($match.Groups[3].Value)"
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
    throw "Python $version is too old. Required: >= 3.10"
}
Write-Host "[OK] Python version: $version" -ForegroundColor Green

$venvDir = Join-Path $PSScriptRoot ".venv"
$venvPy = Join-Path $venvDir "Scripts\python.exe"
$needCreateVenv = $false

if (Test-Path $venvPy) {
    & $venvPy --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Existing venv is invalid, recreating." -ForegroundColor Yellow
        $needCreateVenv = $true
    }
} else {
    $needCreateVenv = $true
}

if ($needCreateVenv) {
    if (Test-Path $venvDir) {
        Remove-Item -Recurse -Force $venvDir
    }
    Write-Step "Creating virtual environment"
    Invoke-RootPython -Info $pyInfo -PyArgs @('-m', 'venv', $venvDir)
    Write-Host "[OK] venv created: $venvDir" -ForegroundColor Green
} else {
    Write-Host "[OK] venv exists: $venvDir" -ForegroundColor Green
}

if (-not $SkipInstall) {
    Write-Step "Installing runtime dependencies"
    & $venvPy -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip/setuptools/wheel"
    }
    $reqMain = Join-Path $PSScriptRoot "requirements.txt"
    if (Test-Path $reqMain) {
        & $venvPy -m pip install -r $reqMain
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install requirements.txt"
        }
    }
    $reqProd = Join-Path $PSScriptRoot "requirements-prod.txt"
    if (Test-Path $reqProd) {
        & $venvPy -m pip install -r $reqProd
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install requirements-prod.txt"
        }
    }
    if (!(Test-Path $reqMain) -and !(Test-Path $reqProd)) {
        throw "No requirements file found."
    }
    Write-Host "[OK] dependency install finished" -ForegroundColor Green
} else {
    Write-Host "[INFO] Skip dependency install (-SkipInstall)" -ForegroundColor Yellow
}

Write-Step "Verifying dependencies"
& $venvPy -c 'import flask, waitress'
if ($LASTEXITCODE -ne 0) {
    throw "Dependency verification failed"
}

Write-Step "Preparing runtime directories"
$bundleData = Join-Path $PSScriptRoot "data"
$bundleApk = Join-Path $bundleData "apk"
$bundleJenkins = Join-Path $bundleData "jenkins_instances"
$bundleLogs = Join-Path $PSScriptRoot "logs"
foreach ($dir in @($bundleData, $bundleApk, $bundleJenkins, $bundleLogs)) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

if (-not $env:APK_DIR) {
    $env:APK_DIR = $bundleApk
}
if (-not $env:JENKINS_INSTANCES_DIR) {
    $env:JENKINS_INSTANCES_DIR = $bundleJenkins
}
if (-not $env:JENKINS_BUILDS_DIR) {
    $env:JENKINS_BUILDS_DIR = (Join-Path $bundleJenkins "default\jobs\Android\builds")
}

if ($CheckOnly) {
    Write-Host "[DONE] Environment check passed (CheckOnly)" -ForegroundColor Green
    exit 0
}

$env:APP_PORTAL_MODE = "admin"
$env:APK_PORT = "$Port"

Write-Step "Starting service"
Write-Host ("[INFO] mode=admin, port={0}" -f $Port) -ForegroundColor Yellow
Write-Host ("[INFO] url=http://127.0.0.1:{0}" -f $Port) -ForegroundColor Yellow
& $venvPy -m waitress "--listen=0.0.0.0:$Port" "admin_wsgi:app"
