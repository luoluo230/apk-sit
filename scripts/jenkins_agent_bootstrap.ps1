#Requires -Version 5.1
param(
    [ValidateSet("build-android", "build-wxminigame")]
    [string]$Role = "build-android",
    [string]$JenkinsMasterUrl = "http://127.0.0.1:8082",
    [string]$NodeName = "",
    [string]$AgentWorkDir = "C:\jenkins-agent"
)

$ErrorActionPreference = "Stop"
$label = if ($Role -eq "build-wxminigame") { "build-wxminigame" } else { "build-android" }
$name = if ($NodeName) { $NodeName } else { "$label-$env:COMPUTERNAME" }

Write-Host "[agent] Bootstrap Jenkins agent name=$name label=$label master=$JenkinsMasterUrl"
New-Item -ItemType Directory -Force -Path $AgentWorkDir | Out-Null

$agentJar = Join-Path $AgentWorkDir "agent.jar"
if (-not (Test-Path $agentJar)) {
    $jarUrl = ($JenkinsMasterUrl.TrimEnd('/') + "/jnlpJars/agent.jar")
    Write-Host "[agent] Download $jarUrl"
    Invoke-WebRequest -Uri $jarUrl -OutFile $agentJar -UseBasicParsing
}

Write-Host @"
[agent] Next steps (manual secret from Jenkins UI):
  1. Jenkins -> Manage Jenkins -> Nodes -> New Node -> Permanent Agent
  2. Name: $name
  3. Remote root: $AgentWorkDir
  4. Labels: $label
  5. Launch: Run from agent with Java Web Start / inbound agent
  6. java -jar $agentJar -url $JenkinsMasterUrl -name $name -secret <SECRET> -workDir `"$AgentWorkDir`"
"@
