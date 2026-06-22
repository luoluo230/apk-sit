#Requires -Version 5.1
param(
    [string]$GameServerRoot = "E:\maclient\game-server",
    [int]$S1Conc = $(if ($env:PRESSURE_TEST_S1_CONC) { [int]$env:PRESSURE_TEST_S1_CONC } else { 10 }),
    [int]$S1Rounds = 5,
    [int]$S2Conc = $(if ($env:PRESSURE_TEST_S2_CONC) { [int]$env:PRESSURE_TEST_S2_CONC } else { 50 }),
    [int]$S2Rounds = 5,
    [switch]$S1Only
)

$ErrorActionPreference = "Stop"
$smokeDir = Join-Path $GameServerRoot "tools\SmokeTest"
$bat = Join-Path $smokeDir "Run-Pressure-Test.bat"
if (-not (Test-Path $bat)) {
    Write-Host "SKIP: Run-Pressure-Test.bat missing"
    exit 0
}

if (-not (Test-NetConnection 127.0.0.1 -Port 15050 -WarningAction SilentlyContinue).TcpTestSucceeded) {
        & powershell -ExecutionPolicy Bypass -File (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path "tools\start_release_stack.ps1") -SkipDocker
}

Push-Location $smokeDir
try {
    $ps1 = Join-Path $smokeDir "Run-Pressure-Test.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -Layer S1 -Rounds $S1Rounds -Concurrency $S1Conc -WaitBetweenRoundsSec 5
    if ($LASTEXITCODE -ne 0) { throw "S1 pressure failed exit=$LASTEXITCODE" }
    if (-not $S1Only) {
        $s2Conc = if ($env:CLOSURE_MODE -eq "1") { 5 } else { $S2Conc }
        $s2Rounds = if ($env:CLOSURE_MODE -eq "1") { 2 } else { $S2Rounds }
        $s2Args = @("-Layer", "S2", "-Rounds", $s2Rounds, "-Concurrency", $s2Conc, "-WaitBetweenRoundsSec", "5")
        if ($env:CLOSURE_MODE -eq "1") {
            $env:PRESSURE_S2_LOGIN_ONLY = "1"
            $s2Args += @("-FixedAccount", "session_gate_user", "-Password", "123456")
        }
        & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 @s2Args
        if ($LASTEXITCODE -ne 0) { throw "S2 pressure failed exit=$LASTEXITCODE" }
    }
} finally {
    Pop-Location
}
Write-Host "PRESSURE S1/S2 GATE PASSED"
exit 0
