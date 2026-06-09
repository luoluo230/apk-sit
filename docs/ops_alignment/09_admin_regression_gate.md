# Admin 管理端回归门禁

更新时间：2026-06-08  
范围：仅 `APP_PORTAL_MODE=admin`（入口 `portals/intranet/wsgi.py`）

## 运行方式

```bash
# 全量门禁（推荐）
py -3 dev/tools/run_admin_regression_gate.py --strict

# 分项
py -3 -m pytest tests/ops_distributed -m fast -q
py -3 dev/tools/ops_platform_smoke.py --project GomeKu --strict
py -3 dev/tools/ops_workbench_chain_audit.py --project GomeKu --strict
py -3 dev/tools/_verify_agent_control.py
```

**前置条件**：Mongo/Redis 已启动；4 进程 GameServer 栈需 `flow-control(start)` 且 `flow-status=success`（live 用例）。

## Ops 页面（8）

| 页面 | URL |
|------|-----|
| 总览 | `/admin/ops-platform` |
| 动作中心 | `/admin/ops-platform/actions` |
| 拓扑编排 | `/admin/ops-platform/topology` |
| 诊断 | `/admin/ops-platform/diagnostics` |
| Agent 管控 | `/admin/ops-platform/agent-control` |
| Agent 详情 | `/admin/ops-platform/agent-detail` |
| 本机 Agent | `/admin/ops-platform/agent-device-local` |
| 变更治理 | `/admin/ops-platform/change-governance` |

## 核心 API（按域）

### 概览 / 集群
- `GET /api/ops-platform/overview`
- `GET /api/ops-platform/events`
- `GET /api/ops-platform/module-map`
- `GET /api/ops-platform/control-plane/summary`
- `POST /api/ops-platform/cluster/sync`

### Agent 管理中心
- `GET /api/ops-platform/agents`
- `GET /api/ops-platform/agents/devices`
- `POST /api/ops-platform/agents/probe-all`
- `POST /api/ops-platform/agents/probe`
- `POST /api/ops-platform/agents/cleanup-expired`
- `GET /api/ops-platform/agent/detail`
- `GET /api/ops-platform/agent/jobs`
- `GET /api/ops-platform/agent/audit`
- `GET|POST /api/ops-platform/agent/policy`
- `POST /api/ops-platform/agent/register|heartbeat|pull|report`

### 服务器运维
- `GET /api/ops-platform/services`
- `POST /api/ops-platform/services/action`（start/stop/restart/status/probe）
- `GET /api/ops-platform/services/logs`

### 拓扑编排
- `GET /api/ops-platform/topology`
- `POST /api/ops-platform/topology/save`
- `POST /api/ops-platform/topology/node/update`
- `POST /api/ops-platform/topology/edge/upsert|delete`
- `POST /api/ops-platform/topology/node/bind-agent`
- `POST /api/ops-platform/topology/auto-bind-agents`
- `POST /api/ops-platform/topology/workbench-mode`
- `GET /api/ops-platform/topology-blueprints`
- `POST /api/ops-platform/flow-smoke`
- `POST /api/ops-platform/stress-test`

### Runtime
- `POST /api/ops-platform/runtime/flow-control`
- `GET /api/ops-platform/runtime/flow-status`
- `GET /api/ops-platform/runtime/active`
- `POST /api/ops-platform/topology/node/start-remote`

### 业务测试
- `GET /api/ops-platform/business-test/catalog`
- `POST /api/ops-platform/business-test/run`

## 模块化拆分后必跑

每次 `gm_legacy.py` / `routes/ops/*` / `services/ops/*` 变更后：

1. `py -3 -m py_compile portals/common/core/routes/gm_legacy.py portals/common/core/routes/ops/*.py portals/common/core/services/ops/*.py`
2. `py -3 dev/tools/run_admin_regression_gate.py --strict --skip-live`
