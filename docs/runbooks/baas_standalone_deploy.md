# 轻度 BaaS 独立部署 Runbook

## 概述

Casual BaaS 可 **完全脱离拓扑 / GameServer / Agent** 单独部署，包含：

- 游戏 REST API（登录、公告、邮件、云存档、排行榜、商城、公会、PVP 等）
- SQLite（开发）或 PostgreSQL（生产）
- Web 功能配置 + **GM 运维台**

## 一键启动（本地）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -Background
```

带 PostgreSQL：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -UsePostgres -Background
```

默认地址：`http://127.0.0.1:5004`

| 入口 | URL |
|------|-----|
| BaaS 首页 | `/admin/baas` |
| 登录 | `/login` |
| 功能配置 | `/admin/projects/{id}/casual-services/{service_id}` |
| GM 运维 | `/admin/projects/{id}/baas-gm/{service_id}` |
| 客户端 Bootstrap | `/api/public/client-bootstrap` |
| 公共 API | `/api/baas/v1/{service_id}/...` |

## 环境变量

| 变量 | 说明 |
|------|------|
| `BAAS_STANDALONE=1` | 独立模式（不加载拓扑 Ops） |
| `PORTAL_SERVER_FRAMEWORKS=baas` | 仅 BaaS 框架 |
| `BAAS_PORT` | 监听端口（默认 5004） |
| `DATABASE_URL` | 设则使用 PostgreSQL |

## 数据库

| 模式 | 说明 |
|------|------|
| SQLite | 默认，`data/apk_site.db`，`init_db()` 自动迁移 `baas_*` 表 |
| PostgreSQL | `docker-compose.baas.yml` 或自建，`DATABASE_URL=postgresql://...` |

表包括：`baas_services`、`baas_players`、`baas_mail_messages`、`baas_wallets`、`baas_gift_codes` 等。

## GM 运维能力

| 功能 | API |
|------|-----|
| 仪表盘 | `GET .../gm/dashboard` |
| 玩家列表/详情 | `GET .../gm/players` |
| 全服/定向邮件 | `POST .../gm/mail/broadcast` |
| 钱包调整 | `POST .../gm/wallet` |
| 礼包码 | `GET/POST .../gm/gift-codes` |
| 排行榜 | `GET/DELETE .../gm/leaderboards/{board_id}` |
| 云存档查看 | `GET .../gm/cloudsave/{player_id}` |

## 客户端

导入 `packages/client_network/baas/`，Bootstrap 后直连 REST。

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1 -Mode baas
```

## 与全量 Portal 的关系

全量 Portal（`:5003`）可通过 `PORTAL_SERVER_FRAMEWORKS=all` 同时挂载拓扑与 BaaS。  
独立 BaaS 使用 `app_baas:app` 入口，体积更小、无 maclient/game-server 依赖。
