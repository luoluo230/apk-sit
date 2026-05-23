param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Env = "staging",
    [string]$Channel = "test",
    [string]$Platform = "android",
    [string]$VersionName = "",
    [Parameter(Mandatory = $true)][string]$CiToken
)

$ErrorActionPreference = "Stop"

$uri = "$BaseUrl/api/gm-ops/quality-gate/ci?project_id=$ProjectId&env=$Env&channel=$Channel&platform=$Platform&version_name=$VersionName&ci_token=$CiToken"

try {
    $resp = Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 30
} catch {
    Write-Error "质量门禁接口调用失败: $($_.Exception.Message)"
    exit 3
}

$resp | ConvertTo-Json -Depth 12

if (-not $resp.ok) {
    Write-Error "质量门禁未通过。"
    exit 4
}

Write-Output "质量门禁通过。"
exit 0
