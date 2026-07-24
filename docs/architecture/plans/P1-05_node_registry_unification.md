# P1-05：Node Registry 统一（Build + Ops + Jenkins）

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 2 周 |
| 依赖 | P0-02（DB 真源）, P1-03（platform capability） |
| 评审项 | W-P1-3, W-P2-4 |

---

## 1. 目标

**一张节点表** 描述：Build Agent（Jenkins label）、Ops Agent（ServerAgent）、控制面；消除 `build_nodes.json`、Ops agent registry、Jenkins 节点三份数据漂移。

---

## 2. 统一模型

```sql
CREATE TABLE infra_nodes (
  node_id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  role TEXT NOT NULL,          -- control | build-android | build-ios | build-wxminigame | runtime
  display_name TEXT,
  host TEXT,
  port INTEGER,
  jenkins_label TEXT,
  jenkins_instance_id TEXT,
  capabilities JSON,           -- {platforms:[], os:[]}
  agent_ws_url TEXT,
  status TEXT,
  last_heartbeat_at TEXT,
  payload JSON,
  created_at TEXT,
  updated_at TEXT
);
```

**同步规则**：

| 来源 | 写入 infra_nodes |
|------|------------------|
| Build node heartbeat | `internal_build_nodes` API |
| cluster.json sync | `cluster_importer` → runtime role |
| Jenkins computer API | 定时 job（可选 Step 4） |

---

## 3. 分步实施

### Step 1：Schema + build_nodes 迁移（3 天）

**动作**

1. `models/db.py` 增加 `infra_nodes` 表
2. `services/build/build_node_service.py` 读写 DB 替代 `data/build_nodes.json`
3. 迁移脚本：`scripts/migrate_build_nodes_json_to_db.py`
4. JSON 文件保留 mirror（`BUILD_NODES_JSON_MIRROR`）

**改文件**

- `models/db.py`
- `services/build/build_node_service.py`
- `routes/internal_build_nodes.py`
- `tests/test_build_grid.py` 更新 fixture

**验收**

- [ ] `/admin/build-nodes` UI 数据来自 DB
- [ ] heartbeat 更新 last_heartbeat_at

---

### Step 2：Ops Agent 并入（4 天）

**动作**

1. `cluster_importer.sync_cluster_to_agents` 写入 `infra_nodes`（role=runtime-*）
2. Ops UI Agent 列表改查 `infra_nodes WHERE role LIKE 'runtime%'`
3. 废弃独立 agent json 文件（双写 1 release）

**依赖**：P1-01 `cluster_importer` 模块

**验收**

- [ ] cluster.json 改 port → sync → Ops 页 + build-nodes 不冲突（不同 role）
- [ ] `tests/test_ops_runtime_service.py` pass

---

### Step 3：Admin 统一节点页（3 天）

**动作**

1. 扩展 `/admin/build-nodes` → `/admin/infra-nodes`（或 Tab：构建 / 运行）
2. 过滤：role、project、status、platform capability
3. Journey precheck 展示「推荐构建节点」来自 infra_nodes

**验收**

- [ ] 单页可见 Android 构建机 + gateway 所在 runtime 节点

---

### Step 4：Jenkins 对账（可选，2 天）

**动作**

1. Cron：`jenkins_manager.sync_node_labels()` 对比 Jenkins computer offline/online
2. 标记 infra_nodes.status=offline

---

## 4. 与 build_grid 关系

`build_grid.resolve_assigned_node(platform)` → 查 `infra_nodes` where `jenkins_label=build-android` and status=online。

---

## 5. 完成定义（DoD）

- [ ] `build_nodes.json` 非真源（可删除或仅 mirror）
- [ ] backup 含 infra_nodes
- [ ] W-P1-3 / W-P2-4 关闭
- [ ] P2-01 Server Release 可复用 infra_nodes 做部署目标
