# P1-05：Node Registry 统一（Build + Ops + Jenkins）

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 2 周 |
| 依赖 | P0-02（DB 真源）, P1-03（platform capability） |
| 评审项 | W-P1-3, W-P2-4 |
| 状态 | **Done**（2026-07-28） |

---

## 1. 目标

**一张节点表** 描述：Build Agent（Jenkins label）、Ops Agent（ServerAgent）、控制面；消除 `build_nodes.json`、Ops agent registry、Jenkins 节点三份数据漂移。

---

## 2. 统一模型

`infra_nodes` SQLite 表（见 `models/db.py`）+ `repositories/infra_nodes_repo.py`。

**同步规则**：

| 来源 | 写入 infra_nodes |
|------|------------------|
| Build node heartbeat | `internal_build_nodes` → `register_or_heartbeat` |
| cluster.json sync | `cluster_importer._sync_cluster_to_agents` → `runtime-*` role |
| Legacy JSON | `scripts/migrate_build_nodes_json_to_db.py` |

`BUILD_NODES_JSON_MIRROR=1` 时保留 JSON mirror（非真源）。

---

## 3. 分步实施

### Step 1：Schema + build_nodes 迁移（3 天） ✅

- [x] `infra_nodes` 表 + repository
- [x] `build_node_service` 读写 DB
- [x] `scripts/migrate_build_nodes_json_to_db.py`
- [x] heartbeat 更新 `last_heartbeat_at`

---

### Step 2：Ops Agent 并入（4 天） ✅

- [x] `cluster_importer` 双写 `infra_nodes`（`runtime-*` role）
- [x] Ops agent registry 保留（双写 release）；统一页读 infra_nodes

**验收**

- [x] build / runtime 不同 role 不冲突
- [x] `test_ops_runtime_service.py` 不受影响

---

### Step 3：Admin 统一节点页（3 天） ✅

- [x] `/admin/infra-nodes`（`/admin/build-nodes` 重定向）
- [x] Tab：构建 / 运行 / 全部
- [x] Journey `recommended_build_node` 来自 infra_nodes

---

### Step 4：Jenkins 对账（可选） ⏸

- Cron `jenkins_manager.sync_node_labels()` — 留待后续

---

## 4. 与 build_grid 关系

`resolve_assigned_node(platform)` 优先返回在线节点的 `jenkins_label`（查 infra_nodes）。

---

## 5. 完成定义（DoD）

- [x] `build_nodes.json` 非真源（mirror only）
- [x] infra_nodes 在 SQLite backup 链路（同 release_orders / ops_agents）
- [x] W-P1-3 / W-P2-4 关闭（统一 registry + DB 真源）
- [x] P2-01 可复用 infra_nodes 做部署目标
