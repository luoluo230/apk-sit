param(
    [string]$AppDir = (Split-Path -Parent $PSScriptRoot),
    [string]$AppName = "apk-site",
    [string]$PublicHost,
    [int]$AppPort = 5003
)

$ErrorActionPreference = 'Stop'

if (-not $PublicHost) {
    throw "PublicHost is required."
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    throw "Run this script in an elevated PowerShell window."
}

$caddy = Get-Command caddy -ErrorAction SilentlyContinue
if (-not $caddy) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Caddy is not installed and winget is unavailable."
    }
    winget install -e --id CaddyServer.Caddy --accept-package-agreements --accept-source-agreements
    $caddy = Get-Command caddy -ErrorAction SilentlyContinue
    if (-not $caddy) {
        throw "Caddy installation failed."
    }
}

$AppDir = (Resolve-Path $AppDir).Path
$caddyfile = Join-Path $AppDir 'Caddyfile'
@"
$PublicHost {
    reverse_proxy 127.0.0.1:$AppPort
}
"@ | Set-Content -Path $caddyfile -Encoding UTF8

try {
    Unregister-ScheduledTask -TaskPath "\" -TaskName "$AppName-caddy" -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {
}

$args = "-NoProfile -ExecutionPolicy Bypass -Command `"& '$($caddy.Source)' run --config '$caddyfile'`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args -WorkingDirectory $AppDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskPath "\" -TaskName "$AppName-caddy" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath "\" -TaskName "$AppName-caddy"

netsh advfirewall firewall delete rule name="$AppName-http" *> $null
netsh advfirewall firewall delete rule name="$AppName-https" *> $null
netsh advfirewall firewall add rule name="$AppName-http" dir=in action=allow protocol=TCP localport=80 | Out-Null
netsh advfirewall firewall add rule name="$AppName-https" dir=in action=allow protocol=TCP localport=443 | Out-Null

Write-Host "[DONE] HTTPS reverse proxy configured for $PublicHost"
