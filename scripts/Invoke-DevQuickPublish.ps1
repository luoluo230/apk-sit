param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [Parameter(Mandatory = $true)]
    [string]$ChannelId,
    [Parameter(Mandatory = $true)]
    [string]$Platform,
    [Parameter(Mandatory = $true)]
    [string]$VersionId,
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [switch]$SkipBuild,
    [switch]$ForceBuild,
    [switch]$NoAutoVerify
)

$ErrorActionPreference = "Stop"

$body = @{
    env_key     = "development"
    channel_id  = $ChannelId
    platform    = $Platform
    version_id  = $VersionId
    skip_build  = [bool]$SkipBuild
    force_build = [bool]$ForceBuild
    auto_verify = -not $NoAutoVerify
} | ConvertTo-Json -Compress

$uri = "$BaseUrl/api/projects/$([uri]::EscapeDataString($ProjectId))/delivery-attempts/quick-publish"

Write-Host "POST $uri"
$response = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json; charset=utf-8" -Body $body -WebSession $global:ApkSiteSession

if (-not $response.ok) {
    throw ($response.error | Out-String)
}

$response.data | ConvertTo-Json -Depth 8
