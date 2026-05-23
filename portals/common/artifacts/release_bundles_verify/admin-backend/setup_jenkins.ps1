param(
    [switch]$CheckOnly,
    [switch]$UseDocker,
    [switch]$StartAfterSetup,
    [int]$JenkinsPort=8080,
    [bool]$InstallJavaIfMissing=$true,
    [bool]$InstallDockerIfMissing=$false,
    [string]$JenkinsImage='jenkins/jenkins:lts-jdk17',
    [string]$JenkinsContainerName='apk-site-jenkins'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "[STEP] $Text" -ForegroundColor Cyan
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $paths = @()
    if ($machinePath) { $paths += $machinePath }
    if ($userPath) { $paths += $userPath }
    if ($paths.Count -gt 0) {
        $env:Path = ($paths -join ';')
    }
}

function Install-WithWinget([string]$PackageId, [string]$Label) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "$Label is missing and winget is unavailable. Install it manually."
    }
    Write-Step "Installing $Label via winget"
    & $winget.Source install -e --id $PackageId --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget failed to install $Label ($PackageId)"
    }
    Refresh-Path
}

function Ensure-Java {
    $java = Get-Command java -ErrorAction SilentlyContinue
    if ($java) {
        Write-Host ("[OK] Java found: {0}" -f $java.Source) -ForegroundColor Green
        return
    }
    if (-not $InstallJavaIfMissing) {
        throw "Java 17+ is required for Jenkins. Install Java or pass -InstallJavaIfMissing `$true."
    }
    Install-WithWinget -PackageId 'Microsoft.OpenJDK.17' -Label 'OpenJDK 17'
    $java = Get-Command java -ErrorAction SilentlyContinue
    if (-not $java) {
        throw "Java install completed but 'java' is still unavailable. Reopen terminal and retry."
    }
    Write-Host ("[OK] Java found after install: {0}" -f $java.Source) -ForegroundColor Green
}

function Ensure-Docker {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) {
        Write-Host ("[OK] Docker found: {0}" -f $docker.Source) -ForegroundColor Green
        return
    }
    if (-not $InstallDockerIfMissing) {
        throw "Docker is required for -UseDocker. Install Docker Desktop or pass -InstallDockerIfMissing `$true."
    }
    Install-WithWinget -PackageId 'Docker.DockerDesktop' -Label 'Docker Desktop'
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker install completed but 'docker' is still unavailable. Reopen terminal and retry."
    }
    Write-Host ("[OK] Docker found after install: {0}" -f $docker.Source) -ForegroundColor Green
}

Write-Step "Preparing Jenkins runtime paths"
$bundleData = Join-Path $PSScriptRoot "data"
$instancesDir = Join-Path $bundleData "jenkins_instances"
$defaultHome = Join-Path $instancesDir "default"
$defaultBuilds = Join-Path $defaultHome "jobs\Android\builds"
$warPath = Join-Path $instancesDir "jenkins.war"
foreach ($dir in @($bundleData, $instancesDir, $defaultHome, $defaultBuilds)) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-Host ("[OK] Jenkins instances dir: {0}" -f $instancesDir) -ForegroundColor Green
Write-Host ("[OK] Jenkins builds dir: {0}" -f $defaultBuilds) -ForegroundColor Green

if ($UseDocker) {
    Write-Step "Checking Docker runtime"
    Ensure-Docker
    Write-Step "Pulling Jenkins image"
    docker pull $JenkinsImage
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull image: $JenkinsImage"
    }
    Write-Host ("[OK] Jenkins image ready: {0}" -f $JenkinsImage) -ForegroundColor Green

    if ($StartAfterSetup -and -not $CheckOnly) {
        Write-Step "Starting Jenkins container"
        $existing = (docker ps -a --filter "name=^/$JenkinsContainerName$" --format "{{.ID}}")
        if ($existing) {
            docker rm -f $JenkinsContainerName | Out-Null
        }
        docker run -d --name $JenkinsContainerName -p "$JenkinsPort`:8080" -p "50000:50000" -v "${defaultHome}:/var/jenkins_home" $JenkinsImage | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start Jenkins container."
        }
        Write-Host ("[OK] Jenkins container started: http://127.0.0.1:{0}" -f $JenkinsPort) -ForegroundColor Green
    }
} else {
    Write-Step "Checking Java runtime"
    Ensure-Java

    if (!(Test-Path $warPath)) {
        Write-Step "Downloading jenkins.war"
        $warUrl = "https://get.jenkins.io/war-stable/latest/jenkins.war"
        Invoke-WebRequest -UseBasicParsing -Uri $warUrl -OutFile $warPath
        if (!(Test-Path $warPath)) {
            throw "jenkins.war download failed."
        }
    }
    Write-Host ("[OK] jenkins.war: {0}" -f $warPath) -ForegroundColor Green

    if ($StartAfterSetup -and -not $CheckOnly) {
        Write-Step "Starting local Jenkins process"
        $env:JENKINS_HOME = $defaultHome
        Start-Process -FilePath "java" -ArgumentList @("-Djenkins.install.runSetupWizard=false", "-jar", $warPath, "--httpPort=$JenkinsPort") -WorkingDirectory $PSScriptRoot | Out-Null
        Write-Host ("[OK] Jenkins process started: http://127.0.0.1:{0}" -f $JenkinsPort) -ForegroundColor Green
    }
}

$envLocalPath = Join-Path $PSScriptRoot ".env.jenkins.local"
@(
    "# Jenkins local bootstrap output",
    "JENKINS_URL=http://127.0.0.1:$JenkinsPort",
    "JENKINS_WAR_PATH=./data/jenkins_instances/jenkins.war",
    "JENKINS_INSTANCES_DIR=./data/jenkins_instances",
    "JENKINS_BUILDS_DIR=./data/jenkins_instances/default/jobs/Android/builds",
    "JENKINS_DOCKER_IMAGE=$JenkinsImage",
    "JENKINS_CONTAINER_NAME=$JenkinsContainerName"
) | Set-Content -Path $envLocalPath -Encoding UTF8
Write-Host ("[OK] Wrote {0}" -f $envLocalPath) -ForegroundColor Green

if ($CheckOnly) {
    Write-Host "[DONE] Jenkins bootstrap check passed (CheckOnly)." -ForegroundColor Green
    exit 0
}

if (-not $StartAfterSetup) {
    if ($UseDocker) {
        Write-Host "[INFO] Docker mode prepared. Run with -StartAfterSetup to launch container." -ForegroundColor Yellow
    } else {
        Write-Host ("[INFO] Local mode prepared. Start command: java -Djenkins.install.runSetupWizard=false -jar ""{0}"" --httpPort={1}" -f $warPath, $JenkinsPort) -ForegroundColor Yellow
    }
}
