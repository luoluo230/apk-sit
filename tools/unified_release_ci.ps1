param(
    [switch]$SkipServer,
    [switch]$SkipUnity,
    [switch]$RequireStack,
    [switch]$ClosureMode,
    [string]$UnityScenario = "smoke",
    [string]$BaseUrl = "http://127.0.0.1:5003",
    [string]$ScopeId = "gomeku:development:1001",
    [string]$UnityProject = "E:\maclient",
    [string]$GameServerRoot = "E:\maclient\game-server"
)

$ErrorActionPreference = "Stop"
if ($ClosureMode -or $env:CLOSURE_MODE -eq "1") {
    $env:CLOSURE_MODE = "1"
    $RequireStack = $true
}
$ApkCore = Join-Path $PSScriptRoot "..\portals\common\core" | Resolve-Path
$ApkRoot = Split-Path $ApkCore -Parent | Split-Path -Parent | Split-Path -Parent | Resolve-Path
$MaclientRoot = if ($env:MACLIENT_ROOT) { $env:MACLIENT_ROOT } else { "E:\maclient" }

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Archive-Evidence([string]$StepName, [string]$LogText) {
    $dest = Join-Path (Split-Path $ApkCore -Parent | Split-Path -Parent | Split-Path -Parent) "docs\evidence\$(Get-Date -Format yyyy-MM-dd)"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $safe = ($StepName -replace '[^\w\-]', '_')
    $path = Join-Path $dest "$safe.log"
    Add-Content -Path $path -Value $LogText
}

Invoke-Step "S0: NetworkContract build + copy" {
    $ncProj = Join-Path $MaclientRoot "shared\NetworkContract\NetworkContract.csproj"
    if (Test-Path $ncProj) {
        dotnet build $ncProj -c Release
        $src = Join-Path $MaclientRoot "shared\NetworkContract\bin\Release\netstandard2.0\NetworkContract.dll"
        $destDir = Join-Path $MaclientRoot "Assets\Plugins\NetworkContract"
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        Copy-Item $src (Join-Path $destDir "NetworkContract.dll") -Force
    } else {
        Write-Warning "NetworkContract project not found: $ncProj"
    }
}

Invoke-Step "S1: Python compile" {
    Set-Location $ApkCore
    Get-ChildItem -Recurse -Include *.py -Path data,models,services,scripts,routes,tests |
        Where-Object { $_.FullName -notmatch 'jenkins-clone|__pycache__' -and $_.Name -notlike '._*' } |
        ForEach-Object {
            py -3 -m py_compile $_.FullName
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
}

Invoke-Step "S1b: pytest" {
    Set-Location $ApkCore
    py -3 -m pytest tests\ -q
}

Invoke-Step "S1c: protocol alignment" {
    Set-Location $ApkCore
    py -3 scripts\protocol_alignment_ci_gate.py
}

Invoke-Step "S1c2: protocol dictionary codegen" {
    Set-Location $ApkCore
    py -3 scripts\codegen_protocol_dictionary.py --check
}

Invoke-Step "S1c3: OpenAPI drift check" {
    Set-Location $ApkCore
    py -3 scripts\generate_openapi.py --check
}

Invoke-Step "S1c4: admin_routes size gate" {
    Set-Location $ApkCore
    py -3 scripts\admin_routes_size_gate.py
}

if (-not $SkipServer) {
    Invoke-Step "S1d: seed release gate fixture" {
        Set-Location $ApkCore
        py -3 scripts\seed_unified_project_delivery.py
        py -3 scripts\seed_release_gate_fixture.py
    }

    Invoke-Step "S2: Web commercial gate" {
        Set-Location $ApkCore
        $env:RELEASE_GATE_BASE_URL = $BaseUrl
        $env:RELEASE_GATE_SCOPE_ID = $ScopeId
        py -3 scripts\commercial_startup_sequence_gate.py
        Archive-Evidence "commercial_gate" "PASS"
    }

    Invoke-Step "S2b: bootstrap gate e2e" {
        Set-Location $ApkCore
        $env:RELEASE_GATE_BASE_URL = $BaseUrl
        if ($env:CLOSURE_MODE -eq "1") {
            py -3 scripts\seed_release_gate_fixture.py --force-update --rollout-percentage 50
            $env:REQUIRE_FORCE_UPDATE = "1"
        }
        py -3 scripts\bootstrap_gate_e2e.py
    }

    if ($RequireStack) {
        Invoke-Step "S2c: transport login matrix" {
            Set-Location $ApkCore
            py -3 scripts\transport_login_matrix.py
        }

        Invoke-Step "S2d: ops platform e2e gate" {
            Set-Location $ApkCore
            py -3 scripts\ops_platform_e2e_gate.py
        }

        Invoke-Step "S2e: client telemetry e2e gate" {
            Set-Location $ApkCore
            py -3 scripts\client_telemetry_e2e_gate.py
        }

        Invoke-Step "S2f: webhook feishu gate" {
            Set-Location $ApkCore
            py -3 scripts\webhook_feishu_gate.py
        }

        Invoke-Step "S2g: redis session gate" {
            Set-Location $ApkCore
            py -3 scripts\redis_session_gate.py
        }

        Invoke-Step "S2h: grafana smoke gate" {
            Set-Location $ApkCore
            py -3 scripts\grafana_smoke_gate.py
        }

        $i18nGate = Join-Path $ApkRoot "scripts\i18n_coverage_gate.py"
        if (Test-Path $i18nGate) {
            Invoke-Step "S2i: i18n coverage gate" {
                py -3 $i18nGate
            }
        }

        $splitBundles = Join-Path $ApkCore "scripts\verify_split_bundles_runtime.ps1"
        $bundlesRoot = Join-Path $ApkCore "release_bundles\admin-backend\start_admin.ps1"
        if ((Test-Path $splitBundles) -and (Test-Path $bundlesRoot)) {
            Invoke-Step "S2j: split bundles runtime" {
                & powershell -ExecutionPolicy Bypass -File $splitBundles -SkipInstall
            }
        } elseif ($env:CLOSURE_MODE -eq "1") {
            throw "S2j FAIL: release_bundles missing — run build_split_deploy_bundles.py"
        }
    }

    $l1Script = Join-Path $GameServerRoot "tools\SmokeTest\run_l1_ci.ps1"
    if (Test-Path $l1Script) {
        $l1Args = @("-ExecutionPolicy", "Bypass", "-File", $l1Script, "-SkipBuild")
        if ($RequireStack -or $env:CLOSURE_MODE -eq "1") { $l1Args += "-RequireGateway" } else { $l1Args += "-L0Only" }
        if ($env:CLOSURE_MODE -eq "1") { $l1Args += "-PreflightOnly" }
        Invoke-Step "S3: game-server L1 CI" {
            & powershell @l1Args
        }
    } else {
        Write-Warning "S3 skipped: $l1Script not found"
    }
} else {
    Write-Host "S2/S3 skipped (-SkipServer)" -ForegroundColor Yellow
}

if (-not $SkipUnity) {
    $unityTimeout = if ($UnityScenario -eq 'session') { 300 } else { 120 }
    $unitySessionArgs = if ($UnityScenario -eq 'session') {
        @"
    game_id='gomeku-fb64779f94b161d0',
    game_key='zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf',
    username='session_gate_user',
    password='123456',
    server_id='game-cn-1',
"@
    } else { "" }
    Invoke-Step "S4: Unity $UnityScenario" {
        Set-Location $ApkCore
        py -3 -c @"
from services.unity_client_hotupdate_runner import run_unity_client_startup_acceptance
import os, sys, shutil
from datetime import date
r = run_unity_client_startup_acceptance(
    unity_project=r'$UnityProject',
    api_base='$BaseUrl',
    scenario='$UnityScenario',
    version_name='1.0.0',
    version_code='12',
    timeout_sec=$unityTimeout,
$unitySessionArgs
)
print(r)
dest = os.path.join(r'$((Split-Path $ApkCore -Parent | Split-Path -Parent | Split-Path -Parent))', 'docs', 'evidence', date.today().isoformat())
os.makedirs(dest, exist_ok=True)
report = os.path.join(r'$UnityProject', 'Library', 'ClientAcceptance', 'client-startup-acceptance-report.json')
if os.path.isfile(report):
    shutil.copy2(report, os.path.join(dest, 'unity-$UnityScenario-report.json'))
if not r.get('passed'):
    sys.exit(1)
"@
    }
} else {
    Write-Host "S4 skipped (-SkipUnity)" -ForegroundColor Yellow
}

Write-Host "`n=== UNIFIED CI PASSED ===" -ForegroundColor Green
