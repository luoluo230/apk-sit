# 入口地图（主路径）

| 用户意图 | 唯一 URL | API | Service 模块 |
|----------|----------|-----|--------------|
| 选 scope | `/admin/projects/{id}/environments/{env}` | `GET .../environment-detail` | `channel_journey_bff.environment_detail` |
| 构建 | `.../channels/{ch}/build` | `POST .../versions/{vid}/quick-build` | `order_build_sync.request_build` |
| 发版 | `.../channels/{ch}/release` | precheck → publish → verify | `order_publish_flow` + `order_crud` |
| 一键发版 | — | `POST .../delivery-attempts/quick-publish` | `order_build_sync.quick_publish_delivery` |
| 客户端读包 | — | `GET /api/public/runtime-bootstrap` | `bundle_service` + gray rollout |
| 客户端兼容 | — | `GET /api/runtime/version-resolve` (deprecated) | `release_context.merge_version_resolve_with_active_bundle` |
| 发布上下文 | — | `GET /api/public/release-config` | `release_context.resolve_release_context` |

## Internal / Webhook

| 路径 | 说明 |
|------|------|
| `POST /api/internal/jenkins/build-complete` | Jenkins HMAC webhook → sync build status |
| `POST /api/webhooks/approval/{provider}` | 外部审批回调 → approve_release_order |
| `GET /api/projects/{id}/build-events` | Build status poll + ETag |
| `GET /api/projects/{id}/build-events/stream` | Build status SSE |

## Legacy（redirect / wrapper）

| Legacy | 替代 |
|--------|------|
| `/admin/build/commercial-release` | `/admin/projects/{id}/overview` |
| `POST .../commercial-release/trigger` | `POST .../quick-build`（带 Deprecation） |
| `POST .../commercial-release/activate` | `precheck` + `publish` via release order |
| `POST /api/gm-ops/release/*` | ReleaseOrder API（deprecated 薄包装） |
| `GET /runtime/version-resolve` | `GET /api/public/runtime-bootstrap` |

## Route 模块（P1+ 拆分）

| 模块 | 职责 |
|------|------|
| `routes/delivery/pages.py` | HTML 页面 |
| `routes/delivery/scope_api.py` | 环境/渠道/scope |
| `routes/delivery/journey_api.py` | Build/Release Journey |
| `routes/delivery/release_orders_api.py` | 发布单 CRUD |
| `routes/delivery/build_events_api.py` | 构建事件 poll/SSE |
| `routes/delivery/public_api.py` | runtime-bootstrap + release-config |
| `routes/internal_jenkins.py` | Jenkins webhook |
| `routes/approval_webhooks.py` | 审批 webhook |
| `routes/gm_ops_release.py` | GM deprecated wrappers |

## Ops 模块（P1-01 拆分后）

| 模块 | 职责 |
|------|------|
| `services/ops/helpers.py` | 薄 facade（render + re-export） |
| `services/ops/topology_registry.py` | 拓扑 CRUD、scoped load/save |
| `services/ops/cluster_importer.py` | cluster.json 同步 |
| `services/ops/agent_registry.py` | Agent 注册、heartbeat |
| `services/ops/runtime_orchestrator.py` | runtime 启停编排 |
| `services/ops/topology_contracts.py` | node contract、端口 |
| `services/ops/diagnostics.py` | 诊断摘要 |
| `services/ops/server_deploy_dispatch.py` | 服务端制品部署入队 |
