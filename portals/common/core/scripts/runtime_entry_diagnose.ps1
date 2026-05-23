param(
  [string]$TargetHost = "127.0.0.1",
  [int[]]$Ports = @(5003,5004,5005)
)

Write-Host "=== Runtime Entrypoint Diagnose ==="
foreach($p in $Ports){
  $conn = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if(-not $conn){
    Write-Host "[$p] NOT LISTENING"
    continue
  }
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)" -ErrorAction SilentlyContinue
  Write-Host "[$p] PID=$($conn.OwningProcess) CMD=$($proc.CommandLine)"
  try{
    $url = "http://${TargetHost}:$p/health"
    $h = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    Write-Host "[$p] /health => $($h.StatusCode)"
  }catch{
    Write-Host "[$p] /health => ERROR $($_.Exception.Message)"
  }
}
Write-Host "=== End ==="
