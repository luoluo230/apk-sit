#Requires -Version 5.1
<#
  Shared helpers: single-instance Portal on 127.0.0.1:5003.
  Dot-source from repo scripts — do not run directly.
#>

function Get-Portal5003Port {
    return 5003
}

function Get-Portal5003LockPath {
    param([string]$RepoRoot)
    if (-not $RepoRoot) {
        throw "RepoRoot required for Get-Portal5003LockPath"
    }
    $dir = Join-Path $RepoRoot "data"
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    return Join-Path $dir ".portal-5003.lock.json"
}

function Get-Portal5003ListenerRows {
    param(
        [int]$Port = 5003,
        [string]$Address = ""
    )
    $rows = @()
    $seen = @{}

    $tcpRows = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($row in $tcpRows) {
        $key = "{0}:{1}:{2}" -f $row.LocalAddress, $row.LocalPort, $row.OwningProcess
        if ($seen.ContainsKey($key)) { continue }
        if ($Address -and $row.LocalAddress -ne $Address -and $row.LocalAddress -ne "0.0.0.0") { continue }
        $seen[$key] = $true
        $rows += [pscustomobject]@{
            LocalAddress = $row.LocalAddress
            LocalPort    = $row.LocalPort
            OwningProcess = $row.OwningProcess
            Source       = "Get-NetTCPConnection"
        }
    }

    if ($rows.Count -eq 0) {
        $pattern = ":$Port\s"
        netstat -ano | Select-String $pattern | ForEach-Object {
            $line = $_.Line.Trim()
            if ($line -notmatch "LISTENING") { return }
            $parts = $line -split "\s+" | Where-Object { $_ -ne "" }
            if ($parts.Count -lt 5) { return }
            $procId = [int]$parts[-1]
            $local = $parts[1]
            if ($Address -and $local -notmatch [regex]::Escape($Address) -and $local -notmatch "0\.0\.0\.0") { return }
            $key = "$local`:$Port`:$procId"
            if ($seen.ContainsKey($key)) { return }
            $seen[$key] = $true
            $rows += [pscustomobject]@{
                LocalAddress = ($local -split ":")[0]
                LocalPort    = $Port
                OwningProcess = $procId
                Source       = "netstat"
            }
        }
    }

    return $rows
}

function Get-Portal5003ListenerPids {
    param([int]$Port = 5003)
    $pids = @(Get-Portal5003ListenerRows -Port $Port | Select-Object -ExpandProperty OwningProcess -Unique)
    $pids = @($pids | Where-Object { $_ -and $_ -gt 0 })
    if ($pids.Count -gt 0) { return $pids }

    # Fallback: orphaned waitress/python processes still advertising this port in cmdline.
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = [string]$_.CommandLine
            if (-not $cmd) { return $false }
            return (
                ($cmd -match "waitress") -and
                ($cmd -match ":$Port\b|port=$Port|--port\s+$Port|127\.0\.0\.1:$Port")
            ) -or (
                ($cmd -match "app_new:app") -and ($cmd -match ":$Port|port\s+$Port")
            )
        } |
        Select-Object -ExpandProperty ProcessId -Unique
}

function Get-Portal5003ProcessInfo {
    param([int]$ProcessId)
    if (-not $ProcessId) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    $name = $proc.Name
    $cmd = [string]$proc.CommandLine
    if ($cmd.Length -gt 160) { $cmd = $cmd.Substring(0, 157) + "..." }
    return [pscustomobject]@{
        ProcessId = $ProcessId
        Name      = $name
        CommandLine = $cmd
    }
}

function Stop-Portal5003Listeners {
    param(
        [int]$Port = 5003,
        [switch]$Quiet
    )
    $pids = @(Get-Portal5003ListenerPids -Port $Port)
    $stopped = @()
    foreach ($procId in $pids) {
        $info = Get-Portal5003ProcessInfo -ProcessId $procId
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            $stopped += $info
            if (-not $Quiet) {
                Write-Host ("[portal5003] stopped PID {0} ({1})" -f $procId, $(if ($info) { $info.Name } else { "unknown" })) -ForegroundColor Yellow
                if ($info -and $info.CommandLine) {
                    Write-Host ("           {0}" -f $info.CommandLine) -ForegroundColor DarkYellow
                }
            }
        }
        catch {
            if (-not $Quiet) {
                Write-Warning ("[portal5003] failed to stop PID {0}: {1}" -f $procId, $_.Exception.Message)
            }
        }
    }
    if ($stopped.Count -gt 0) {
        Start-Sleep -Seconds 1
    }
    return $stopped
}

function Assert-SinglePortal5003Listener {
    param(
        [int]$Port = 5003,
        [string]$BaseUrl = "http://127.0.0.1:5003"
    )
    $rows = @(Get-Portal5003ListenerRows -Port $Port)
    $pids = @($rows | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 })
    if ($pids.Count -eq 0) {
        throw "Portal :$Port is not listening"
    }
    if ($pids.Count -gt 1) {
        $detail = ($pids | ForEach-Object {
            $info = Get-Portal5003ProcessInfo -ProcessId $_
            if ($info) { "PID $($info.ProcessId) $($info.Name)" } else { "PID $_" }
        }) -join "; "
        throw "Multiple Portal listeners on :$Port ($detail). Run scripts\Stop-Portal5003.ps1"
    }
    try {
        $resp = Invoke-WebRequest -Uri "$($BaseUrl.TrimEnd('/'))/health" -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -ne 200) {
            throw "Portal /health returned $($resp.StatusCode)"
        }
    }
    catch {
        throw "Portal /health failed on $BaseUrl : $($_.Exception.Message)"
    }
    return [pscustomobject]@{
        Port = $Port
        ProcessId = $pids[0]
        ListenerCount = $rows.Count
        BaseUrl = $BaseUrl
    }
}

function Test-Portal5003AgentPullReady {
    param(
        [string]$BaseUrl = "http://127.0.0.1:5003",
        [string]$AgentToken = "ops-write-key-2026"
    )
    $body = @{
        node_id  = "ops-cn-1"
        agent_id = "agent-local-cn-1"
        limit    = 3
        token    = $AgentToken
    } | ConvertTo-Json -Compress
    $headers = @{
        "Content-Type"  = "application/json"
        "X-Agent-Token" = $AgentToken
    }
    $resp = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/api/ops-platform/agent/pull" `
        -Method Post -Headers $headers -Body $body -TimeoutSec 8
    $jobs = @($resp.jobs | Where-Object { $_ })
    foreach ($job in $jobs) {
        $status = [string]$job.status
        if ($status -in @("SUCCESS", "FAILED", "CANCELED", "TIMEOUT")) { continue }
        if (-not [string]$job.action_type) {
            return [pscustomobject]@{
                Ok = $false
                Reason = "job $($job.job_id) missing action_type (stale Portal code path)"
                Jobs = $jobs.Count
            }
        }
    }
    return [pscustomobject]@{ Ok = $true; Reason = "ok"; Jobs = $jobs.Count }
}

function Write-Portal5003Lock {
    param(
        [string]$RepoRoot,
        [int]$ProcessId,
        [string]$BaseUrl = "http://127.0.0.1:5003",
        [string]$StartedBy = ""
    )
    $path = Get-Portal5003LockPath -RepoRoot $RepoRoot
    $payload = @{
        pid        = $ProcessId
        base_url   = $BaseUrl
        started_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
        started_by = $StartedBy
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $path -Encoding UTF8
    return $path
}

function Remove-Portal5003Lock {
    param([string]$RepoRoot)
    $path = Get-Portal5003LockPath -RepoRoot $RepoRoot
    if (Test-Path $path) {
        Remove-Item -Path $path -Force
    }
}

function Wait-Portal5003Healthy {
    param(
        [string]$BaseUrl = "http://127.0.0.1:5003",
        [int]$TimeoutSec = 120
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $url = "$($BaseUrl.TrimEnd('/'))/health"
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) { return $true }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}
