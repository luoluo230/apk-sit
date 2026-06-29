param(
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [string]$ProjectId = "GomeKu",
    [string]$EnvKey = "development",
    [string]$ChannelId = "1001",
    [string]$Username = "admin",
    [string]$Password = "admin123"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "smoke_delivery_scope.py"
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "py"
    $pyArgs = @("-3", $script)
} else {
    $pyArgs = @($script)
}

$pyArgs += @(
    "--base-url", $BaseUrl,
    "--project-id", $ProjectId,
    "--env-key", $EnvKey,
    "--channel-id", $ChannelId,
    "--username", $Username,
    "--password", $Password
)

& $python @pyArgs
exit $LASTEXITCODE
