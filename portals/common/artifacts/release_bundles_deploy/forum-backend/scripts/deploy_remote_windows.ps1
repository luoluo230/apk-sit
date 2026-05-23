param(
    [string]$ComputerName,
    [string]$RemoteAppDir = "C:\apk-site",
    [string]$PublicHost = "",
    [string]$PublicEip = "",
    [string]$PublicUrl = "",
    [string]$AppName = "apk-site",
    [string]$AppUser = "",
    [int]$AppPort = 5003,
    [string]$ApkDir = "",
    [switch]$EnableCaddy,
    [switch]$InstallPythonIfMissing,
    [switch]$InstallJava,
    [switch]$OpenFirewall = $true,
    [System.Management.Automation.PSCredential]$Credential
)

$ErrorActionPreference = 'Stop'

if (-not $ComputerName) {
    throw "ComputerName is required."
}

if (-not $Credential) {
    $Credential = Get-Credential -Message "Enter Windows server credentials for $ComputerName"
}

$AppDir = Split-Path -Parent $PSScriptRoot
$StageDir = Join-Path $env:TEMP ("apk-site-stage-" + [guid]::NewGuid().ToString("N"))
$ZipPath = Join-Path $env:TEMP ("apk-site-" + [guid]::NewGuid().ToString("N") + ".zip")

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
robocopy $AppDir $StageDir /MIR /XD .git venv __pycache__ logs backups data | Out-Null
Compress-Archive -Path (Join-Path $StageDir '*') -DestinationPath $ZipPath -Force

$session = New-PSSession -ComputerName $ComputerName -Credential $Credential
try {
    $remoteZip = Join-Path $env:TEMP ([IO.Path]::GetFileName($ZipPath))
    Invoke-Command -Session $session -ScriptBlock {
        param($dir)
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    } -ArgumentList $RemoteAppDir

    Copy-Item -ToSession $session -Path $ZipPath -Destination $remoteZip

    Invoke-Command -Session $session -ScriptBlock {
        param($zip, $dest)
        $expandDir = Join-Path $env:TEMP ("apk-site-expand-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $expandDir | Out-Null
        Expand-Archive -Path $zip -DestinationPath $expandDir -Force
        robocopy $expandDir $dest /E | Out-Null
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $expandDir -Recurse -Force -ErrorAction SilentlyContinue
    } -ArgumentList $remoteZip, $RemoteAppDir

$remoteApkDir = if ($ApkDir) { $ApkDir } else { Join-Path $RemoteAppDir 'data\apk' }
    $remoteAppUser = if ($AppUser) { $AppUser } else { $Credential.UserName.Split('\')[-1] }

    Invoke-Command -Session $session -ScriptBlock {
        param($dir, $name, $user, $port, $apkDir, $hostName, $eip, $url, $caddy, $installPython, $installJava, $openFirewall)
        $script = Join-Path $dir 'scripts\cloud_deploy_windows.ps1'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script `
            -AppDir $dir `
            -AppName $name `
            -AppUser $user `
            -AppPort $port `
            -ApkDir $apkDir `
            -PublicHost $hostName `
            -PublicEip $eip `
            -PublicUrl $url `
            -EnableCaddy:$caddy `
            -InstallPythonIfMissing:$installPython `
            -InstallJava:$installJava `
            -OpenFirewall:$openFirewall
    } -ArgumentList $RemoteAppDir, $AppName, $remoteAppUser, $AppPort, $remoteApkDir, $PublicHost, $PublicEip, $PublicUrl, $EnableCaddy.IsPresent, $InstallPythonIfMissing.IsPresent, $InstallJava.IsPresent, $OpenFirewall.IsPresent
}
finally {
    if ($session) {
        Remove-PSSession $session
    }
    Remove-Item $StageDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
}

Write-Host "[DONE] Remote Windows deployment finished."
