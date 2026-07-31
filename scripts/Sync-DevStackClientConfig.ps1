#Requires -Version 5.1
<#
.SYNOPSIS
  Align maclient Unity assets for local dev-stack (Portal :5003 + Gateway :15050).

.DESCRIPTION
  Patches HotUpdateConfig.asset and ProtocolNetworkSettings.asset without opening Unity.
  Optionally runs HotUpdateConfigSyncCli via Unity batchmode when -UseUnity is set.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1
  powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1 -UseUnity
#>
param(
    [string]$MaclientRoot = "",
    [string]$PortalBaseUrl = "http://127.0.0.1:5003",
    [string]$GatewayWs = "ws://127.0.0.1:15050/ws",
    [string]$Profile = "Development",
    [string]$Channel = "wechat",
    [switch]$UseUnity
)

$ErrorActionPreference = "Stop"

function Resolve-MaclientRoot([string]$Candidate) {
    if (-not [string]::IsNullOrWhiteSpace($Candidate) -and (Test-Path $Candidate)) {
        return (Resolve-Path $Candidate).Path
    }
    foreach ($path in @($env:MACLIENT_ROOT, $env:UNITY_PROJECT_PATH, "E:\maclient")) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return (Resolve-Path $path).Path
        }
    }
    throw "maclient root not found. Set MACLIENT_ROOT or pass -MaclientRoot."
}

function Resolve-UnityExecutable {
    foreach ($path in @($env:UNITY_PATH, $env:UNITY_EDITOR)) {
        if (-not [string]::IsNullOrWhiteSpace($path) -and (Test-Path $path)) {
            return $path
        }
    }
    $hubRoot = Join-Path ${env:ProgramFiles} "Unity\Hub\Editor"
    if (Test-Path $hubRoot) {
        $latest = Get-ChildItem $hubRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($latest) {
            $exe = Join-Path $latest.FullName "Editor\Unity.exe"
            if (Test-Path $exe) { return $exe }
        }
    }
    return $null
}

function Set-UnityYamlScalar {
    param(
        [string]$Path,
        [string]$FieldName,
        [string]$Value
    )
    if (-not (Test-Path $Path)) {
        throw "Missing asset: $Path"
    }
    $content = [System.IO.File]::ReadAllText($Path)
    $escaped = [regex]::Escape($FieldName)
    $pattern = '(?m)^(\s*' + $escaped + ':\s).*?(\r?\n|$)'
    if (-not [regex]::IsMatch($content, $pattern)) {
        throw "Field not found in $Path : $FieldName"
    }
    $replacement = '${1}' + $Value + '${2}'
    $updated = [regex]::Replace($content, $pattern, $replacement, 1)
    if ($updated -eq $content) {
        return $false
    }
    [System.IO.File]::WriteAllText($Path, $updated)
    return $true
}

function Sync-HotUpdateConfigAsset {
    param(
        [string]$Root,
        [string]$BaseUrl,
        [string]$DevProfile,
        [string]$DevChannel
    )
    $asset = Join-Path $Root "Assets\Content\Resources\HotUpdateConfig.asset"
    $base = ($(if ($BaseUrl) { $BaseUrl } else { "" })).Trim().TrimEnd("/")
    if ([string]::IsNullOrWhiteSpace($base)) {
        throw "PortalBaseUrl is empty"
    }

    $changed = @()
    foreach ($pair in @(
            @{ Field = "Profile"; Value = $DevProfile },
            @{ Field = "Channel"; Value = $DevChannel },
            @{ Field = "RuntimeBootstrapUrl"; Value = $base },
            @{ Field = "VersionResolveUrl"; Value = $base },
            @{ Field = "RuntimeChannel"; Value = "development" },
            @{ Field = "ExpectedUploadEnvironment"; Value = $DevProfile },
            @{ Field = "BlockStartupOnConfigSyncFailure"; Value = "0" },
            @{ Field = "RequireConfigPatchManifestSignature"; Value = "0" },
            @{ Field = "RequireCodePatchManifestSignature"; Value = "0" },
            @{ Field = "ArtifactGateStrictMode"; Value = "0" }
        )) {
        if (Set-UnityYamlScalar -Path $asset -FieldName $pair.Field -Value $pair.Value) {
            $changed += $pair.Field
        }
    }
    return @{ Path = $asset; Changed = $changed }
}

function Sync-ProtocolNetworkSettingsAsset {
    param(
        [string]$Root,
        [string]$Endpoint
    )
    $asset = Join-Path $Root "Assets\Resources\Protocol\ProtocolNetworkSettings.asset"
    if (-not (Test-Path $asset)) {
        throw "Missing asset: $asset"
    }

    $content = [System.IO.File]::ReadAllText($asset)
    $updated = $content

    $updated = [regex]::Replace(
        $updated,
        '(?m)^(\s*EndpointUrl:\s).*?(\r?\n|$)',
        '${1}' + $Endpoint + '${2}',
        1
    )
    $updated = [regex]::Replace(
        $updated,
        '(?m)^(\s*ActiveEnvironmentId:\s).*?(\r?\n|$)',
        '${1}dev${2}',
        1
    )
    $updated = [regex]::Replace(
        $updated,
        '(?ms)(- EnvironmentId: dev\r?\n\s+DisplayName:.*?\r?\n\s+EndpointUrl:\s).*?(\r?\n|$)',
        '${1}' + $Endpoint + '${2}'
    )

    if ($updated -eq $content) {
        return @{ Path = $asset; Changed = @() }
    }
    [System.IO.File]::WriteAllText($asset, $updated)
    return @{ Path = $asset; Changed = @("EndpointUrl", "ActiveEnvironmentId", "dev preset") }
}

function Invoke-UnitySyncCli {
    param(
        [string]$Root,
        [string]$BaseUrl,
        [string]$Endpoint,
        [string]$DevProfile,
        [string]$DevChannel
    )
    $unity = Resolve-UnityExecutable
    if (-not $unity) {
        throw "Unity executable not found for -UseUnity. Set UNITY_PATH or UNITY_EDITOR."
    }

    $log = Join-Path $Root "Temp\DevStackConfigSync.log"
    $logDir = Split-Path $log -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    $args = @(
        "-batchmode",
        "-quit",
        "-projectPath", $Root,
        "-executeMethod", "HotUpdateConfigSyncCli.ExecuteFromCommandLine",
        "-releaseEnvironment", $DevProfile,
        "-releaseChannel", $DevChannel,
        "-portalBaseUrl", $BaseUrl,
        "-gatewayWs", $Endpoint,
        "-logFile", $log
    )

    Write-Host "[sync] Unity batchmode HotUpdateConfigSyncCli"
    $proc = Start-Process -FilePath $unity -ArgumentList $args -NoNewWindow -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        if (Test-Path $log) {
            Get-Content $log -Tail 40 | ForEach-Object { Write-Host $_ }
        }
        throw "Unity sync failed exit=$($proc.ExitCode). See $log"
    }
}

$maclient = Resolve-MaclientRoot $MaclientRoot
$portal = ($(if ($PortalBaseUrl) { $PortalBaseUrl } else { "" })).Trim().TrimEnd("/")
$gateway = ($(if ($GatewayWs) { $GatewayWs } else { "" })).Trim()

Write-Host "=== Sync-DevStackClientConfig ===" -ForegroundColor Cyan
Write-Host "[sync] maclient=$maclient"
Write-Host "[sync] portal=$portal gateway=$gateway profile=$Profile channel=$Channel"

if ($UseUnity) {
    Invoke-UnitySyncCli -Root $maclient -BaseUrl $portal -Endpoint $gateway -DevProfile $Profile -DevChannel $Channel
}

$hot = Sync-HotUpdateConfigAsset -Root $maclient -BaseUrl $portal -DevProfile $Profile -DevChannel $Channel
$net = Sync-ProtocolNetworkSettingsAsset -Root $maclient -Endpoint $gateway

Write-Host "[sync] HotUpdateConfig changed: $($hot.Changed -join ', ')"
Write-Host "[sync] ProtocolNetworkSettings changed: $($net.Changed -join ', ')"
Write-Host "=== Sync-DevStackClientConfig DONE ===" -ForegroundColor Green
