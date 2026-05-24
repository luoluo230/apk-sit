# 运维平台接入手册（ServerAgent + Legacy GM）

## 1. 目标
将 `gameserver-standalone/tools/ServerAgent` 作为每台服务器的守护进程，统一接入内网运维平台：
- 节点探活（agent status）
- 单节点上线/下线
- 全节点一键启停
- 经典 GM 操作（玩家、资源、邮件）

## 2. 现有架构对接点
- ServerAgent WebSocket：支持 `start/stop/status` 命令。
- Legacy GmWebServer：提供 `cluster-state/start-all/stop-all/agent-status` 以及经典 GM 表单接口。
- Intranet 新页面：
  - `GET /admin/gm-classic`
  - `GET /admin/ops-platform`

## 3. 节点配置（内网运维平台）
通过 `运维平台 -> 节点配置(JSON)` 或 API `POST /api/gm-legacy/nodes` 配置：

```json
[
  {
    "id": "cn-dev-01",
    "name": "华东开发01",
    "base_url": "http://10.10.10.11:8080",
    "username": "gm",
    "password": "***",
    "server_id": "game-cn-1",
    "project_id": "GomeKu",
    "env": "dev",
    "channel": "1001",
    "enabled": true,
    "tags": ["cn", "dev"]
  }
]
```

字段说明：
- `base_url`：legacy GM 控制台所在地址（不带 `/gm` 也可）。
- `username/password`：legacy GM 登录账号。
- `server_id`：用于调用 `agent-status` 与上线/下线目标。
- `project_id/env/channel`：用于后续自动路由节点（同项目上下文自动命中）。

## 4. 接口清单
- 节点配置
  - `GET /api/gm-legacy/nodes`
  - `POST /api/gm-legacy/nodes`
- 经典 GM 动作
  - `POST /api/gm-classic/action`
- 运维动作
  - `POST /api/ops-platform/action`
  - `GET /api/ops-platform/summary`

## 5. 动作映射
### 5.1 经典 GM
`/api/gm-classic/action` 的 `action` 支持：
- `search_player`
- `player_status`
- `adjust_currency`
- `adjust_item`
- `hero_edit`
- `stage_update`
- `idle_recompute`
- `send_mail`
- `send_broadcast`
- `save_template`
- `save_activity`
- `save_announcement`
- `script_task`

### 5.2 运维
`/api/ops-platform/action` 的 `action` 支持：
- `agent_status`
- `online`
- `offline`
- `start_all`
- `stop_all`

## 6. 部署建议
1. 每个物理机/云主机部署一个 `ServerAgent` 进程，绑定固定端口。
2. 每个逻辑节点在 GM 配置中维护 `AgentWs`，确保 `agent-status` 与 `cluster-state` 可达。
3. 内网平台节点表按环境、项目、渠道维护，不建议多环境复用同一节点条目。
4. 正式服建议配合审批流与审计日志联动（下一阶段可接入审批强制门禁）。

## 7. 已知约束
- 当前桥接层通过 legacy GM 页面接口执行动作，返回为页面解析结果，不是纯 JSON 原生 RPC。
- 若 legacy GM 登录策略变化，需要同步调整桥接登录逻辑。
- `server_id` 需要和 GM 集群配置一致，否则 `agent-status`/上下线会失败。
