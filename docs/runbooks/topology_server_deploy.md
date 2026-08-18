# 中重度拓扑服务器 — 独立部署 Runbook

## 概述

拓扑服务器框架（`topology_server`）用于 Agent / Runtime / 拓扑绑定 / runtime-bootstrap，配合 `packages/client_network/topology` 客户端模块。

## 一键启动（开发）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-DevStack.ps1 -SkipGameServer
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `PORTAL_SERVER_FRAMEWORKS=topology` | 仅加载拓扑服务端框架 |
| `PORTAL_SERVER_FRAMEWORKS=all` | 拓扑 + BaaS 全量 |

## 客户端

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1 -Mode topology
```

Bootstrap：`GET /api/public/runtime-bootstrap`

## Portal 管理

- 服务器管理 → **中重度服务器** Tab
- 拓扑画布、绑定、运行态均在卡片深链中操作

## 部署包

在 Portal「服务器管理 → 中重度服务器」页下载 **架构部署压缩包**，解压合并到 apk-site 仓库根目录后按本 Runbook 启动。
