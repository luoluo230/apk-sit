#Requires -Version 5.1
<#
.SYNOPSIS
  Export a standalone client network module zip (topology | baas).

.DESCRIPTION
  Each zip is self-contained. Import into Unity via Import-ClientNetworkModule.ps1.
  Base project keeps only packages/client_network/stubs until modules are imported.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\Export-ClientNetworkModule.ps1 -Module baas
  powershell -ExecutionPolicy Bypass -File scripts\Export-ClientNetworkModule.ps1 -Module topology -MaclientRoot E:\maclient
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("topology", "baas")]
    [string]$Module,
    [string]$OutputPath = "",
    [string]$MaclientRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pkgRoot = Join-Path $repoRoot "packages/client_network/$Module"
$manifestPath = Join-Path $pkgRoot "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "Missing manifest: $manifestPath" }

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputPath = Join-Path $repoRoot "dist/client-network-$Module-$stamp.zip"
}
$outDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
if (Test-Path $OutputPath) { Remove-Item $OutputPath -Force }

$temp = Join-Path ([IO.Path]::GetTempPath()) ("client_network_export_" + [Guid]::NewGuid().ToString("N"))
$bundle = Join-Path $temp "ClientNetworkModule"
New-Item -ItemType Directory -Path $bundle -Force | Out-Null

Copy-Item $manifestPath (Join-Path $bundle "manifest.json")
Copy-Item (Join-Path $repoRoot "packages/client_network/stubs") (Join-Path $bundle "stubs") -Recurse -Force
Copy-Item (Join-Path $pkgRoot "Runtime") (Join-Path $bundle "Runtime") -Recurse -Force

$commonHttp = Join-Path $repoRoot "packages/client_network/common/Runtime/PortalHttp.cs"
if (Test-Path $commonHttp) {
    Copy-Item $commonHttp (Join-Path $bundle "Runtime/PortalHttp.cs") -Force
}

$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$asmdefName = $manifest.asmdef
$asmdefPath = Join-Path $bundle "$asmdefName"
@"
{
  "name": "$($asmdefName -replace '\.asmdef$','')",
  "rootNamespace": "$($manifest.namespace)",
  "references": [],
  "includePlatforms": [],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "autoReferenced": true,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
"@ | Set-Content -Path $asmdefPath -Encoding UTF8

if (-not [string]::IsNullOrWhiteSpace($MaclientRoot) -and (Test-Path $MaclientRoot)) {
    if ($Module -eq "topology") {
        foreach ($rel in @($manifest.maclient_export_roots)) {
            $src = Join-Path $MaclientRoot ($rel -replace '/', '\')
            if (Test-Path $src) {
                $dest = Join-Path $bundle ("maclient/" + $rel)
                $parent = Split-Path $dest -Parent
                if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                if (Test-Path $src -PathType Container) {
                    Copy-Item $src $dest -Recurse -Force
                } else {
                    Copy-Item $src $dest -Force
                    if (Test-Path ($src + ".meta")) { Copy-Item ($src + ".meta") ($dest + ".meta") -Force }
                }
            }
        }
    }
    if ($Module -eq "baas") {
        $playMode = Join-Path $MaclientRoot "Assets/Modules/BaasNetwork/Tests/PlayMode"
        if (Test-Path $playMode) {
            Copy-Item $playMode (Join-Path $bundle "Tests/PlayMode") -Recurse -Force
        }
    }
}

if (Test-Path (Join-Path $pkgRoot "README.md")) {
    Copy-Item (Join-Path $pkgRoot "README.md") (Join-Path $bundle "README.md") -Force
}

$deployGuide = if ($Module -eq "topology") {
    "docs/runbooks/topology_server_deploy_step_by_step.md"
} else {
    "docs/runbooks/baas_server_deploy_step_by_step.md"
}
$guidePath = Join-Path $repoRoot $deployGuide
if (Test-Path $guidePath) {
    Copy-Item $guidePath (Join-Path $bundle "SERVER_DEPLOY_GUIDE.md") -Force
}

$readme = @"
# 客户端网络模块：$Module

| 字段 | 值 |
|------|-----|
| 配对服务端 | $($manifest.pairs_with) |
| Unity 导入目录 | $($manifest.import_target) |
| 程序集 | $($manifest.namespace) |
| Bootstrap | $($manifest.bootstrap) |

---

## 前提

- Unity 2022.3+ / Unity 6（与 maclient 一致）
- **基础工程**仅保留 ``ClientNetworkModuleGate``（``MAClient.Network.Abstractions``），**不要**预置本模块代码
- 服务端已按 ``SERVER_DEPLOY_GUIDE.md`` 部署并 health 正常

---

## 步骤 1 — 解压

``````powershell
Expand-Archive -Path client-network-$Module-*.zip -DestinationPath E:\tmp\$Module-module -Force
``````

解压后根目录为 ``ClientNetworkModule/``，内含 ``manifest.json``、``Runtime/``、``stubs/``。

---

## 步骤 2 — 导入 Unity 工程

在 **apk-site** 仓库根目录执行：

``````powershell
powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 `
  -Module $Module `
  -MaclientRoot E:\maclient `
  -SourceDir E:\tmp\$Module-module\ClientNetworkModule
``````

脚本会：

1. 复制 ``Runtime/`` 到 ``$($manifest.import_target)/Runtime/``
2. 写入 ``$($manifest.asmdef)``
3. 同步 ``stubs/Runtime/ClientNetworkModuleGate.cs`` 到 Abstractions（若缺失）
4. 更新 ``Assets/StreamingAssets/client_network_modules.json``

---

## 步骤 3 — Unity 编译验证

1. 打开 Unity Hub → 打开 maclient 工程
2. 等待脚本编译完成（Console 无 error）
3. 确认程序集 ``$($asmdefName -replace '\.asmdef$','')`` 存在
4. 运行时 ``ClientNetworkModuleGate.Has$(($Module.Substring(0,1).ToUpper() + $Module.Substring(1)))Module`` 为 true

---

## 步骤 4 — Bootstrap 联调

1. 在 HotUpdateConfig / 项目配置填入 Portal 下发的 ``game_id`` / ``game_key``
2. 启动游戏或 PlayMode 测试拉取 ``$($manifest.bootstrap)``
3. 验证网络注入（拓扑：``gateway_ws``；BaaS：``public_api_base``）

---

## 步骤 5 — 卸载模块（恢复干净基线）

``````powershell
powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 `
  -Module $Module -MaclientRoot E:\maclient -Remove
``````

---

## 包内文件说明

| 路径 | 说明 |
|------|------|
| ``Runtime/`` | 模块运行时 C# |
| ``Runtime/PortalHttp.cs`` | 共享 HTTP GET（bootstrap） |
| ``stubs/`` | 基线 Gate，导入时合并到 Abstractions |
| ``manifest.json`` | 模块元数据 |
| ``SERVER_DEPLOY_GUIDE.md`` | 配套服务端逐步部署教程 |
| ``Tests/PlayMode/`` | （baas）可选 PlayMode E2E |

---

## 注意

- **同一产品**通常只导入 **topology** 或 **baas** 之一；双栈需明确架构评审
- 拓扑包若含 ``maclient/`` 子目录，Import 会额外合并 GameServer 网络栈与协议资产
- 详细服务端部署见 ``SERVER_DEPLOY_GUIDE.md``
"@
Set-Content -Path (Join-Path $bundle "README_IMPORT.md") -Value $readme -Encoding UTF8

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($bundle, $OutputPath)
Remove-Item $temp -Recurse -Force
Write-Host "[export] wrote $OutputPath" -ForegroundColor Green
