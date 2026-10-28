# 入口地图（主路径）

人用的发版只有这五扇门。渠道 Journey 页面会跳到版本与管线或发版，不要再把它们写成唯一入口。

| 用户意图 | 唯一 URL | API | Service 模块 |
|----------|----------|-----|--------------|
| 看线上与下一步 | `/admin/projects/{id}/release-hub` | `GET /api/projects/{id}/release-hub` | `release_hub_bff` + `flow_storyline_service` |
| 执行发版 | `/admin/projects/{id}/release` | `GET /api/projects/{id}/release-console` | `release_console_bff` |
| 管版本与管线 | `/admin/projects/{id}/versions?env_key=` | `GET /api/projects/{id}/version-delivery-matrix` | `version_delivery_matrix_service` |
| 看构建与产物 | `/admin/projects/{id}/build-history` | 构建历史 API | `build_history_service` |
| 看发布历史 | `/admin/projects/{id}/release-orders` | 发布单列表 | `order_crud` |
| 触发构建 | 版本行或发版台 | `POST .../versions/{vid}/quick-build` | `order_build_sync.request_build` |
| 客户端读包 | — | `GET /api/public/runtime-bootstrap` | `bundle_service` |
| 发布上下文 | — | `GET /api/public/release-config` | `release_context.resolve_release_context` |

无 `env_key` 打开版本页时，302 到 `env_key=development`。

## Internal / Webhook

| 路径 | 说明 |
|------|------|
| `POST /api/internal/jenkins/build-complete` | Jenkins HMAC webhook → sync build status |
| `POST /api/webhooks/approval/{provider}` | 外部审批回调 → approve_release_order |
| `GET /api/projects/{id}/build-events` | Build status poll + ETag |
| `GET /api/projects/{id}/build-events/stream` | Build status SSE |

## Legacy（跳转，不是主路径）

| Legacy | 替代 |
|--------|------|
| `.../channels/{ch}/build` | `/versions?env_key&channel_id&platform&action=create_vc` |
| `.../channels/{ch}/release` | `/versions?...&action=edit_release` |
| `/admin/versions` | `/admin/projects` |
| `/admin/build/commercial-release` | `/admin/projects/{id}/overview` |
| `POST .../commercial-release/trigger` | `POST .../quick-build` |
| `POST /api/gm-ops/release/*` | ReleaseOrder API |
| `GET /runtime/version-resolve` | `GET /api/public/runtime-bootstrap` |

## Route 模块

| 模块 | 职责 |
|------|------|
| `routes/delivery/pages.py` | 发版中心、发版、发布历史 HTML |
| `routes/admin/pages_project_workspace.py` | 版本与管线页 |
| `routes/delivery/release_hub_api.py` | 发版中心 BFF |
| `routes/delivery/release_console_api.py` | 发版执行 BFF |
| `routes/admin/api_versions.py` | 版本与交付线矩阵 |
| `routes/delivery/release_orders_api.py` | 发布单 CRUD |
| `routes/delivery/journey_api.py` | 旧 Journey API，页面已跳转 |
| `routes/delivery/public_api.py` | runtime-bootstrap + release-config |

## Ops 模块（P1-01 拆分后）

| 模块 | 职责 |
|------|------|
| `services/ops/helpers.py` | 薄 facade |
| `services/ops/topology_registry.py` | 拓扑 CRUD |
| `services/ops/cluster_importer.py` | cluster.json 同步 |
| `services/ops/agent_registry.py` | Agent 注册、heartbeat |
| `services/ops/runtime_orchestrator.py` | runtime 启停 |
| `services/ops/topology_contracts.py` | node contract、端口 |
| `services/ops/diagnostics.py` | 诊断摘要 |
| `services/ops/server_deploy_dispatch.py` | 服务端制品部署入队 |

部署模式见 [docs/runbooks/deployment_topology.md](../runbooks/deployment_topology.md)。
