param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Env = "staging",
    [string]$Channel = "test",
    [string]$Platform = "android",
    [string]$VersionName = "",
    [Parameter(Mandatory = $true)][string]$CiToken,
    [string]$GameId = "",
    [string]$GameKey = "",
    [string]$SessionCookie = "",
    [string]$CsrfToken = "",
    [string]$OutFile = "docs/ops_center_go_live_evidence.md",
    [string]$OutJson = "docs/ops_center_go_live_evidence.json"
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "ops_center_go_live_evidence.py"
if (-not (Test-Path $scriptPath)) {
    throw "未找到脚本: $scriptPath"
}

$pyArgs = @(
    $scriptPath,
    "--base-url", $BaseUrl,
    "--project-id", $ProjectId,
    "--env", $Env,
    "--channel", $Channel,
    "--platform", $Platform,
    "--version-name", $VersionName,
    "--ci-token", $CiToken,
    "--out-md", $OutFile,
    "--out-json", $OutJson
)

if ($GameId) { $pyArgs += @("--game-id", $GameId) }
if ($GameKey) { $pyArgs += @("--game-key", $GameKey) }
if ($SessionCookie) { $pyArgs += @("--session-cookie", $SessionCookie) }
if ($CsrfToken) { $pyArgs += @("--csrf-token", $CsrfToken) }

python @pyArgs
if ($LASTEXITCODE -ne 0) {
    throw "证据脚本执行失败，退出码: $LASTEXITCODE"
}

Write-Output "证据报告已生成: $OutFile"
Write-Output "原始证据 JSON: $OutJson"
