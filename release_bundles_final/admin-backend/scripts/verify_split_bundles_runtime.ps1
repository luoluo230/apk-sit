param(
    [string]$BundlesRoot = "",
    [int]$AdminPort = 5503,
    [int]$ForumPort = 5505,
    [int]$PlayerStaticPort = 58080,
    [bool]$SkipInstall = $true
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "[STEP] $Text" -ForegroundColor Cyan
}

function Assert-ExitCodeZero([int]$ExitCode, [string]$Message) {
    if ($ExitCode -ne 0) {
        throw "$Message (exit=$ExitCode)"
    }
}

function Get-ListeningPids([int]$Port) {
    $lines = netstat -ano | findstr ":$Port"
    if (-not $lines) {
        return @()
    }
    $pids = @()
    foreach ($line in @($lines)) {
        if ($line -match "LISTENING") {
            $tokens = ($line -split "\s+") | Where-Object { $_ -ne "" }
            if ($tokens.Count -gt 0) {
                $lastToken = $tokens[$tokens.Count - 1]
                $id = 0
                if ([int]::TryParse($lastToken, [ref]$id)) {
                    $pids += $id
                }
            }
        }
    }
    return $pids | Select-Object -Unique
}

function Stop-PortProcesses([int]$Port) {
    $listeningPids = Get-ListeningPids -Port $Port
    foreach ($procId in $listeningPids) {
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } catch {}
    }
    Start-Sleep -Milliseconds 500
}

function Wait-HttpStatus([string]$Url, [int[]]$AllowedStatusCodes, [int]$TimeoutSec = 40) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2 -MaximumRedirection 0 -ErrorAction SilentlyContinue
            if ($response -and ($AllowedStatusCodes -contains [int]$response.StatusCode)) {
                return [int]$response.StatusCode
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Timeout waiting URL: $Url"
}

function Assert-UrlClosed([string]$Url) {
    try {
        Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 1 | Out-Null
        throw "URL still reachable after stop: $Url"
    } catch {
        if ($_.Exception.Message -like "URL still reachable*") {
            throw
        }
    }
}

function Run-CheckOnly([string]$ScriptPath, [bool]$CanSkipInstall) {
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath, "-CheckOnly")
    if ($CanSkipInstall -and $SkipInstall) {
        $args += "-SkipInstall"
    }
    & powershell @args
    Assert-ExitCodeZero -ExitCode $LASTEXITCODE -Message "CheckOnly failed: $ScriptPath"
}

function Start-Bundle([string]$ScriptPath, [int]$Port, [bool]$CanSkipInstall) {
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath, "-Port", $Port)
    if ($CanSkipInstall -and $SkipInstall) {
        $args += "-SkipInstall"
    }
    $process = Start-Process -FilePath "powershell" -ArgumentList $args -PassThru
    return $process.Id
}

function Stop-Bundle([int]$RootProcessId, [int]$Port) {
    try {
        Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
    Stop-PortProcesses -Port $Port
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $BundlesRoot) {
    $BundlesRoot = Join-Path $root "release_bundles"
}
$BundlesRoot = (Resolve-Path $BundlesRoot).Path
$adminScript = Join-Path $BundlesRoot "admin-backend\start_admin.ps1"
$forumScript = Join-Path $BundlesRoot "forum-backend\start_forum.ps1"
$playerStaticScript = Join-Path $BundlesRoot "player-static\serve_static.ps1"

foreach ($required in @($adminScript, $forumScript, $playerStaticScript)) {
    if (-not (Test-Path $required)) {
        throw "Missing script: $required"
    }
}

Write-Step "Admin bundle CheckOnly"
Run-CheckOnly -ScriptPath $adminScript -CanSkipInstall $true

Write-Step "Forum bundle CheckOnly"
Run-CheckOnly -ScriptPath $forumScript -CanSkipInstall $true

Write-Step "Player-static bundle CheckOnly"
Run-CheckOnly -ScriptPath $playerStaticScript -CanSkipInstall $false

$adminProcessId = 0
$forumProcessId = 0
$playerProcessId = 0

try {
    Write-Step "Start admin bundle runtime"
    Stop-PortProcesses -Port $AdminPort
    $adminProcessId = Start-Bundle -ScriptPath $adminScript -Port $AdminPort -CanSkipInstall $true
    $adminHealthCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/health" -f $AdminPort) -AllowedStatusCodes @(200) -TimeoutSec 60
    $adminPageCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/admin" -f $AdminPort) -AllowedStatusCodes @(200, 302) -TimeoutSec 30
    Write-Host ("[OK] admin health={0}, /admin={1}" -f $adminHealthCode, $adminPageCode) -ForegroundColor Green
    Stop-Bundle -RootProcessId $adminProcessId -Port $AdminPort
    Assert-UrlClosed -Url ("http://127.0.0.1:{0}/health" -f $AdminPort)
    Write-Host "[OK] admin stopped cleanly" -ForegroundColor Green

    Write-Step "Start forum bundle runtime"
    Stop-PortProcesses -Port $ForumPort
    $forumProcessId = Start-Bundle -ScriptPath $forumScript -Port $ForumPort -CanSkipInstall $true
    $forumHealthCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/health" -f $ForumPort) -AllowedStatusCodes @(200) -TimeoutSec 60
    $forumPageCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/forum" -f $ForumPort) -AllowedStatusCodes @(200) -TimeoutSec 30
    Write-Host ("[OK] forum health={0}, /forum={1}" -f $forumHealthCode, $forumPageCode) -ForegroundColor Green
    Stop-Bundle -RootProcessId $forumProcessId -Port $ForumPort
    Assert-UrlClosed -Url ("http://127.0.0.1:{0}/health" -f $ForumPort)
    Write-Host "[OK] forum stopped cleanly" -ForegroundColor Green

    Write-Step "Start player-static runtime"
    Stop-PortProcesses -Port $PlayerStaticPort
    $playerProcessId = Start-Bundle -ScriptPath $playerStaticScript -Port $PlayerStaticPort -CanSkipInstall $false
    $playerHomeCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/" -f $PlayerStaticPort) -AllowedStatusCodes @(200) -TimeoutSec 40
    $playerAboutCode = Wait-HttpStatus -Url ("http://127.0.0.1:{0}/about/company/index.html" -f $PlayerStaticPort) -AllowedStatusCodes @(200) -TimeoutSec 20
    Write-Host ("[OK] player-static /={0}, /about/company/index.html={1}" -f $playerHomeCode, $playerAboutCode) -ForegroundColor Green
    Stop-Bundle -RootProcessId $playerProcessId -Port $PlayerStaticPort
    Assert-UrlClosed -Url ("http://127.0.0.1:{0}/" -f $PlayerStaticPort)
    Write-Host "[OK] player-static stopped cleanly" -ForegroundColor Green

    Write-Host ""
    Write-Host "[DONE] Split bundles runtime verification passed." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    if ($adminProcessId -gt 0) { Stop-Bundle -RootProcessId $adminProcessId -Port $AdminPort }
    if ($forumProcessId -gt 0) { Stop-Bundle -RootProcessId $forumProcessId -Port $ForumPort }
    if ($playerProcessId -gt 0) { Stop-Bundle -RootProcessId $playerProcessId -Port $PlayerStaticPort }
}
