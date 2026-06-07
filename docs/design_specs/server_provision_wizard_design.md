# 开服向导 / Provision API 设计

更新时间：2026-06-06  
状态：设计稿（待实现）  
关联：`拓扑编排详细设计方案.md`、`node_contract_registry.json`、`07_ecosystem_integration.md`

## 1. 目标

为**通用游戏服框架**提供「开新区 / 开新服 / 扩实例」的一键能力，在**不重建整图**的前提下：

1. 自动创建拓扑节点（命名规则可配置）
2. 自动连线（Auth/Ops → Game，Game → Redis/Mongo）
3. Agent / Service 占位（可延后绑定真实 Agent）
4. 可选：保存拓扑 → 同步 `cluster.json` → 远端启动

与蓝图区别：蓝图是**冷启动整图**；开服向导是**在已有生产拓扑上增量扩服**。

## 2. 适用场景

| 场景 | `provision_type` | 说明 |
|------|------------------|------|
| 新开逻辑服（区服） | `new_shard` | 新增 1 个 `business_main`，独立 `ServerId` |
| 同服水平扩容 | `scale_out` | 同 shard 下再加 Game 实例（副本/分线） |
| 新环境克隆 | `env_clone` | 从模板拓扑复制到新 `env_key`（P2） |

本设计首期只做 **`new_shard`** 与 **`scale_out`**。

## 3. 命名规则（通用，非项目绑定）

配置键：`OPS_PROVISION_NAMING`（JSON，按 `project_id` 可覆盖）

```json
{
  "default": {
    "shard_id_pattern": "{region}-{seq:03d}",
    "node_id_pattern": "game-{region}-{seq:03d}",
    "display_name_pattern": "游戏服 {region}-{seq:03d}",
    "region_token": "cn",
    "seq_scope": "project_env_role"
  }
}
```

| 占位符 | 含义 |
|--------|------|
| `{region}` | 区服标识，请求可覆盖 |
| `{seq}` / `{seq:03d}` | 自增序号，scope 内唯一 |
| `{project}` | 项目 ID 小写 |
| `{env}` | 环境 key |
| `{date}` | `YYYYMMDD` |
| `{preset}` | preset_id 短名 |

**序号来源**：扫描当前 scoped 拓扑中同 `role=business` 的节点，取 max(seq)+1。  
**冲突检测**：`node_id` / `server_id` 在拓扑 + `nodes` 配置 + `cluster.json` 三处均不可重复。

## 4. API

### 4.1 预检（Dry-run）

`POST /api/ops-platform/provision/preview`

```json
{
  "project_id": "GomeKu",
  "env_key": "production",
  "topology_id": "topology-gomeku-production-default",
  "provision_type": "new_shard",
  "region": "cn",
  "preset_id": "business_main",
  "anchor_node_id": "auth-cn-1",
  "options": {
    "auto_wire": true,
    "wire_infra": ["redis_cache", "mongo_db"],
    "wire_control": ["auth_service", "ops_service"],
    "create_agent_placeholder": true,
    "sync_cluster": false,
    "start_after_sync": false
  }
}
```

响应：

```json
{
  "ok": true,
  "preview": {
    "node_id": "game-cn-007",
    "server_id": "game-cn-007",
    "display_name": "游戏服 cn-007",
    "edges_to_create": [
      {"from": "auth-cn-1", "to": "game-cn-007", "note": "tcp:session"},
      {"from": "ops-cn-1", "to": "game-cn-007", "note": "tcp:control"},
      {"from": "game-cn-007", "to": "redis-cache-cn-1", "note": "structured-auto"},
      {"from": "game-cn-007", "to": "mongo-db-cn-1", "note": "structured-auto"}
    ],
    "agent_placeholder": {
      "agent_id": "agent-game-cn-007",
      "status": "PLACEHOLDER",
      "bind_after": "manual_or_auto_bind"
    },
    "warnings": []
  }
}
```

### 4.2 执行

`POST /api/ops-platform/provision/execute`

请求体同 preview，增加：

```json
{
  "confirm": true,
  "idempotency_key": "provision-20260606-cn-007",
  "node_id": "game-cn-007"
}
```

执行步骤（事务性，失败可部分回滚并返回 `rollback_hints`）：

1. `_resolve_topology_context`
2. `_allocate_provision_identity()` — 命名 + 冲突校验
3. `_find_anchor_nodes()` — 解析 Auth/Ops/Redis/Mongo（拓扑内按 role 或显式 ID）
4. `_create_provision_game_node()` — 复用 `structured/add-new-target` 逻辑或内联
5. `_apply_provision_edges()` — 复用 `_apply_topology_blueprint_edges` 的 pair 模式
6. `_upsert_agent_placeholder()` — registry V2，`registration_origin=provision.placeholder`
7. `_save_topology_scoped`
8. 若 `sync_cluster=true` → `_sync_topology_to_game_server`
9. 若 `start_after_sync=true` → `topology/node/start-remote` 或 agent job `start`
10. `log_audit("ops_platform_provision_execute", ...)`

响应含 `trace_id`、`created_node`、`edges`、`sync`、`start_job_id`。

### 4.3 列表 / 历史

`GET /api/ops-platform/provision/history?project_id=&limit=20`

写入 event log + 可选 `OPS_PROVISION_HISTORY` 配置。

## 5. 向导 UI（拓扑工作台入口）

入口：

- 总览看板卡片：「开服向导」（链到 workbench `?wizard=provision`）
- 拓扑工具栏按钮：「开服」
- Agent 详情：「在此 Agent 上开新服」（预填 `device_id` / `agent_id`）

步骤（4 步）：

| 步 | 内容 |
|----|------|
| 1 类型 | 新开逻辑服 / 水平扩容；区服 region；preset（默认 business_main） |
| 2 命名 | 展示 preview 生成的 ID/名称，可手工改（触发冲突重检） |
| 3 连线 | 勾选自动连线目标：Auth、Ops、Redis、Mongo（默认全选） |
| 4 落地 | Agent 占位 / 立即 sync cluster / 启动；确认执行 |

完成后跳转：拓扑画布高亮新节点 + Agent 管控「待绑定」过滤。

## 6. 与控制面模块关系

```
开服向导
  → 拓扑（SoT）
  → cluster.json（运行时）
  → Agent 占位 → Agent 管控（绑定/探活）
  → 动作执行（start/health_check，带 node_id + trace_id）
  → 诊断（开服后自动跑 onboarding check）
```

## 7. 权限与审批

| 操作 | 权限 | 审批 |
|------|------|------|
| preview | `ops.platform.view` | 无 |
| execute（仅拓扑） | `ops.platform.execute` | 无 |
| execute + sync + start | `ops.platform.execute` | 高危：`start` 走 `gm_ops_action` 审批 |

## 8. 实现分期

| 阶段 | 交付 |
|------|------|
| P0 | `preview` + `execute` API；命名规则；自动连线；Agent 占位；audit |
| P1 | 向导 UI；开服后诊断联动；project 级 nodes 列表过滤 |
| P2 | `scale_out` 策略；跨 env 克隆；Gateway 分服 metadata 提示 |

## 9. 复用现有代码

| 能力 | 复用 |
|------|------|
| 加节点 | `ops_platform_structured_add_new_target` / `add-from-preset` |
| 批量边 | `_apply_topology_blueprint_edges` |
| 保存/sync | `_save_topology_scoped`、`_sync_topology_to_game_server` |
| Agent | `_upsert_agents_from_topology`、`_load_scope_agent_bindings` |
| 启动 | `ops_platform_topology_node_start_remote` |

## 10. 验收

- [ ] preview 不写入任何存储
- [ ] execute 后拓扑可见新 Game，Auth/Ops/Infra 边正确
- [ ] save/sync 后 `cluster.json` 含新 `ServerId`，且热重载仅影响新服
- [ ] Agent 占位可在 Agent 管控看到，绑定后 probe PASS
- [ ] 同一 `idempotency_key` 重复 execute 返回相同结果，不重复建节点
