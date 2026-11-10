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

## 本机验收清单（P5-01 Wave1）

| 项 | 状态 | 证据 / 说明 |
|----|------|-------------|
| Portal `:5003` 可启动 | PASS | `scripts/Start-Portal5003.ps1 -Background` |
| `bootstrap_gate_e2e.py` | PASS | `docs/evidence/2026-11-10/OPEN-2026-11-10-08.json` |
| DevStack 全栈（含 GameServer） | PASS | `server_release_devstack_e2e` deployed；证据 `OPEN-2026-11-10-09.json` |
| `runtime-bootstrap` 200 | PARTIAL | 缺完整 topology scope 时 400；有 scope 的 bootstrap_gate 已 PASS |
| 生产拓扑独立栈 | BLOCKED | 目标机 env + TLS（OPS） |

## Portal 管理

- 服务器管理 → **中重度服务器** Tab
- 拓扑画布、绑定、运行态均在卡片深链中操作

## 部署包

在 Portal「服务器管理 → 中重度服务器」页下载 **架构部署压缩包**，解压合并到 apk-site 仓库根目录后按本 Runbook 启动。
