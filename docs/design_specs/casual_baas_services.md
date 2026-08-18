# 轻度休闲 BaaS（Passport 模式）

| 项 | 值 |
|---|---|
| Admin 路由 | `/admin/projects/{project_id}/casual-services/{service_id}` |
| Admin API | `/api/projects/{pid}/baas/services/{service_id}` |
| Public API | `/api/baas/v1/{service_id}/...` |
| Bootstrap | `GET /api/public/baas-bootstrap` |
| 模板 | `casual_services_console.html` |

## 四模块拆分

详见 [`server_framework_modules.md`](server_framework_modules.md)：

- `topology_server` + `topology_client`（拓扑 / runtime-bootstrap）
- `casual_baas_server` + `baas_client`（BaaS REST / baas-bootstrap）
- 统一客户端入口：`GET /api/public/client-bootstrap`

## server_mode 分流

| `server_mode` | 行为 |
|---------------|------|
| `topology`（默认） | 现有拓扑 / Agent / Runtime / Server Release |
| `casual_baas` | 休闲服务控制台 + Portal REST BaaS，隐藏拓扑发版项 |

项目字段：`server_mode`、`baas_service_id`（首个 service UUID）。

## 功能模块（Feature Catalog）

| key | 名称 | Phase |
|-----|------|-------|
| login | 登录/账号 | 1 |
| announce | 公告 | 1 |
| mail | 邮件 | 1 |
| cloudsave | 云存档 | 1 |
| leaderboard | 排行榜 | 2 |
| economy | 经济/商城 | 2 |
| achievement | 成就 | 2 |
| gift | 礼包 | 2 |
| guild | 公会 | 3 |
| battlepass | 战令/月卡 | 3 |
| periodic_task | 周期任务 | 3 |
| compliance | 防沉迷/实名 | 4 |
| pvp | PVP 战斗同步 | 4 |

## Public API 鉴权

- `X-Baas-Service-Id` + `X-Baas-Api-Key`（服务端密钥）
- `Authorization: Bearer <player_token>`（玩家操作）

## UI checklist（Passport 对标）

- [ ] 左窄图标栏 + 功能树侧栏
- [ ] 顶栏：功能名 + 配置 ID 复制
- [ ] 右侧配置卡片：开关、表单、保存
- [ ] 功能未启用时显示引导开启
- [ ] 项目卡「休闲服务」入口（仅 casual_baas）

## 验收（Phase 1）

不启拓扑：游客登录 → 读公告 → 收邮件 → 写云存档。
