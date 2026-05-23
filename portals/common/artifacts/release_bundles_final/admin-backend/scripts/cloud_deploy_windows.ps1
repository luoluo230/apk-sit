param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [string]$AppName = "apk-site",
    [string]$AppUser = $env:USERNAME,
    [int]$AppPort = 5003,
    [int]$PlayerPort = 5004,
    [string]$ApkDir = "",
    [string]$PublicHost = "",
    [string]$PublicEip = "",
    [string]$PublicUrl = "",
    [switch]$EnableCaddy,
    [switch]$InstallPythonIfMissing,
    [switch]$InstallJava,
    [switch]$OpenFirewall = $true
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) {
    Write-Host "[INFO] $msg"
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-PythonSpec {
    $candidates = @(
        "C:\python\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe"
    )
    foreach ($candidate in $candidates) {
        try {
            if ((Test-Path $candidate) -and $candidate -match '\.exe$') {
                & $candidate --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    return @{
                        FilePath = $candidate
                        PrefixArgs = @()
                    }
                }
            }
        } catch {
        }
    }

    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pyLauncher) {
        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    }
    if ($pyLauncher -and $pyLauncher.Source) {
        try {
            & $pyLauncher.Source -3 --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    FilePath = $pyLauncher.Source
                    PrefixArgs = @('-3')
                }
            }
        } catch {
        }
    }

    $pythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    }
    if ($pythonCmd -and $pythonCmd.Source) {
        try {
            & $pythonCmd.Source --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return @{
                    FilePath = $pythonCmd.Source
                    PrefixArgs = @()
                }
            }
        } catch {
        }
    }

    return $null
}

function Ensure-Python {
    $python = Get-PythonSpec
    if ($python) { return $python }

    if (-not $InstallPythonIfMissing) {
        throw "Python not found. Re-run with -InstallPythonIfMissing or install Python 3.10+ first."
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python not found and winget is unavailable."
    }

    Write-Info "Installing Python with winget"
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $python = Get-PythonSpec
    if (-not $python) {
        throw "Python installation finished but python command is still unavailable."
    }
    return $python
}

function Ensure-Caddy {
    $cmd = Get-Command caddy -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Caddy is not installed and winget is unavailable."
    }
    Write-Info "Installing Caddy with winget"
    winget install -e --id CaddyServer.Caddy --accept-package-agreements --accept-source-agreements
    $cmd = Get-Command caddy -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Caddy installation finished but caddy command is still unavailable."
    }
    return $cmd.Source
}

function Ensure-Java {
    if (-not $InstallJava) { return }
    if (Get-Command java -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Java is not installed and winget is unavailable."
    }
    Write-Info "Installing OpenJDK 17 with winget"
    winget install -e --id EclipseAdoptium.Temurin.17.JRE --accept-package-agreements --accept-source-agreements
}

function Update-EnvFile {
    param(
        [string]$EnvPath,
        [hashtable]$Values
    )

    $lines = @()
    if (Test-Path $EnvPath) {
        $lines = Get-Content $EnvPath
    }

    $seen = @{}
    $output = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ($line -match '^\s*#' -or $line -notmatch '=') {
            $output.Add($line)
            continue
        }
        $key = $line.Split('=', 2)[0].Trim()
        if ($Values.ContainsKey($key)) {
            $output.Add("$key=$($Values[$key])")
            $seen[$key] = $true
        } else {
            $output.Add($line)
        }
    }
    foreach ($key in $Values.Keys) {
        if (-not $seen.ContainsKey($key)) {
            $output.Add("$key=$($Values[$key])")
        }
    }
    Set-Content -Path $EnvPath -Value $output -Encoding UTF8
}

function Register-TaskAction {
    param(
        [string]$TaskName,
        [string]$Execute,
        [string]$Arguments,
        [string]$WorkingDirectory
    )

    $taskPath = "\"
    try {
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    } catch {
    }

    $action = New-ScheduledTaskAction -Execute $Execute -Argument $Arguments -WorkingDirectory $WorkingDirectory
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskPath $taskPath -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskPath $taskPath -TaskName $TaskName
}

function Wait-ForHttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            return Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 8
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    throw "Service did not become healthy in time: $Url"
}

function Open-PortalLogWindow {
    param(
        [string]$Title,
        [string]$LogPath
    )

    $displayText = "$($Title): $($LogPath)"
    $command = "Write-Host '$displayText'; if (!(Test-Path '$LogPath')) { New-Item -ItemType File -Path '$LogPath' | Out-Null }; Get-Content '$LogPath' -Wait"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', $command
    ) -WindowStyle Normal | Out-Null
}

if (-not (Test-Admin)) {
    throw "Run this script in an elevated PowerShell window."
}

$AppDir = (Resolve-Path $AppDir).Path
if (-not $ApkDir) {
    $ApkDir = Join-Path $AppDir 'data\apk'
}

if (-not $PublicUrl -and $PublicEip) {
    $PublicUrl = "http://${PublicEip}"
}

$pythonSpec = Ensure-Python
Ensure-Java

Write-Info "Preparing directories"
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir 'logs') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir 'data') | Out-Null
New-Item -ItemType Directory -Force -Path $ApkDir | Out-Null

$envPath = Join-Path $AppDir '.env'
if (-not (Test-Path $envPath) -and (Test-Path (Join-Path $AppDir '.env.example'))) {
    Copy-Item (Join-Path $AppDir '.env.example') $envPath
}
if (-not (Test-Path $envPath)) {
    New-Item -ItemType File -Path $envPath | Out-Null
}

$envValues = @{
    APK_DIR   = $ApkDir
    APK_PORT  = "$AppPort"
    ADMIN_PORT = "$AppPort"
    PLAYER_PORT = "$PlayerPort"
    APK_HOST  = "0.0.0.0"
    APK_DEBUG = "false"
    USE_SQLITE = "true"
    SQLITE_MIRROR_JSON = "false"
}
if ($PublicUrl) {
    $envValues["PUBLIC_URL"] = $PublicUrl
} elseif ($PublicHost) {
    $envValues["EXTERNAL_DOMAIN"] = $PublicHost
} elseif ($PublicEip) {
    $envValues["PUBLIC_URL"] = "http://${PublicEip}"
}
Update-EnvFile -EnvPath $envPath -Values $envValues

$venvDir = Join-Path $AppDir 'venv'
if (-not (Test-Path $venvDir)) {
    Write-Info "Creating virtual environment"
    & $pythonSpec.FilePath @($pythonSpec.PrefixArgs + @('-m', 'venv', $venvDir))
}

$venvPython = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment python not found: $venvPython"
}

Write-Info "Installing Python dependencies"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $AppDir 'requirements.txt')
if (Test-Path (Join-Path $AppDir 'requirements-prod.txt')) {
    & $venvPython -m pip install -r (Join-Path $AppDir 'requirements-prod.txt')
}

Write-Info "Migrating JSON data into SQLite"
& $venvPython (Join-Path $AppDir 'scripts\migrate_json_to_sqlite.py')

$runScript = Join-Path $AppDir 'scripts\start_dual_portals.ps1'
Write-Info "Starting dual portals"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runScript -AppDir $AppDir -AdminPort $AppPort -PlayerPort $PlayerPort
Open-PortalLogWindow -Title 'Admin portal log' -LogPath (Join-Path $AppDir 'logs\admin-portal.log')
Open-PortalLogWindow -Title 'Player portal log' -LogPath (Join-Path $AppDir 'logs\player-portal.log')

if ($OpenFirewall) {
    Write-Info "Opening Windows Firewall for application port"
    netsh advfirewall firewall delete rule name="$AppName-$AppPort" *> $null
    netsh advfirewall firewall add rule name="$AppName-$AppPort" dir=in action=allow protocol=TCP localport=$AppPort | Out-Null
    netsh advfirewall firewall delete rule name="$AppName-$PlayerPort" *> $null
    netsh advfirewall firewall add rule name="$AppName-$PlayerPort" dir=in action=allow protocol=TCP localport=$PlayerPort | Out-Null
}

if ($EnableCaddy) {
    if (-not $PublicHost) {
        throw "-EnableCaddy requires -PublicHost."
    }
    $caddyExe = Ensure-Caddy
    $caddyfile = Join-Path $AppDir 'Caddyfile'
    $schemeUrl = if ($PublicUrl) { $PublicUrl } else { "https://$PublicHost" }
    @"
$PublicHost {
    reverse_proxy 127.0.0.1:$AppPort
}
"@ | Set-Content -Path $caddyfile -Encoding UTF8

    $caddyArgs = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$caddyExe' run --config '$caddyfile'`""
    Write-Info "Registering startup task for Caddy HTTPS proxy"
    Register-TaskAction -TaskName "$AppName-caddy" -Execute "powershell.exe" -Arguments $caddyArgs -WorkingDirectory $AppDir

    if ($OpenFirewall) {
        netsh advfirewall firewall delete rule name="$AppName-http" *> $null
        netsh advfirewall firewall delete rule name="$AppName-https" *> $null
        netsh advfirewall firewall add rule name="$AppName-http" dir=in action=allow protocol=TCP localport=80 | Out-Null
        netsh advfirewall firewall add rule name="$AppName-https" dir=in action=allow protocol=TCP localport=443 | Out-Null
    }

    if (-not $PublicUrl) {
        Update-EnvFile -EnvPath $envPath -Values @{ PUBLIC_URL = $schemeUrl }
    }
}

$healthUrl = "http://127.0.0.1:$AppPort/health"
$health = Wait-ForHttpOk -Url $healthUrl
$playerHealthUrl = "http://127.0.0.1:$PlayerPort/health"
$playerHealth = Wait-ForHttpOk -Url $playerHealthUrl

Write-Host ""
Write-Host "[DONE] Windows cloud deployment finished."
Write-Host "App dir:     $AppDir"
Write-Host "Admin port:  $AppPort"
Write-Host "Player port: $PlayerPort"
Write-Host "APK dir:     $ApkDir"
Write-Host "Health:      $($health.Content.Trim())"
Write-Host "Player:      $($playerHealth.Content.Trim())"
if ($PublicHost) {
    Write-Host "Public host: $PublicHost"
}
if ($PublicEip) {
    Write-Host "Public EIP:  $PublicEip"
}
if ($PublicUrl) {
    Write-Host "Public URL:  $PublicUrl"
}
if ($EnableCaddy) {
    Write-Host "HTTPS:       enabled via Caddy"
}
