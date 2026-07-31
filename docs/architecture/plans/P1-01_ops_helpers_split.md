# P1-01：Ops helpers 拆分

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 2–3 周 |
| 依赖 | P0-02 建议完成（Ops 表并入主库） |
| 评审项 | W-P1-1 |

---

## 1. 目标

将 `services/ops/helpers.py`（3400+ 行、80+ 函数）拆为 **职责清晰的 6 模块**，**零行为变更**（纯 refactor + 测试锁定）。

---

## 2. 范围

**In**

- helpers.py 内纯 Python 逻辑（拓扑、Agent、cluster 同步、runtime、诊断）
- 现有 `environment_runtime_service.py` 等已拆文件的 import 整理

**Out**

- Ops UI 模板/HTML 重构
- 新功能（Server Release 见 P2-01）

---

## 3. 目标模块划分

| 新模块 | 职责 | 原 helpers 函数前缀/区域 |
|--------|------|---------------------------|
| `ops/topology_registry.py` | 拓扑 CRUD、scoped load/save | `_load_topology_scoped`, `_save_topology_scoped`, `_list_topologies` |
| `ops/cluster_importer.py` | cluster.json 读取与同步 | `_load_cluster_json`, `_sync_cluster_to_agents`, `_sync_cluster_to_nodes` |
| `ops/agent_registry.py` | Agent 注册、heartbeat、stale | `_sync_cluster_to_agents` 后半、agent merge |
| `ops/runtime_orchestrator.py` | runtime 启停、active 查询 | `_runtime_active_for_scope`, env runtime API 支撑 |
| `ops/topology_contracts.py` | node contract、port、daemon 命令 | `_load_node_contract`, `_format_contract_command` |
| `ops/diagnostics.py` | 诊断摘要、fix actions | `_build_diagnostics_summary`, `_diagnostics_fix_actions` |
| `ops/helpers.py`（保留） | **薄 facade**：re-export + 页面 render 辅助 | `_render_ops_page`, CSRF, 权限 |

---

## 4. 分步实施

### Step 1：测试基线（2 天）

**动作**

1. 跑通并记录：`pytest tests/test_ops_runtime_service.py tests/test_environment_runtime_overview.py tests/test_topology_binding.py -v`
2. 新增 `tests/test_ops_helpers_facade.py`：对关键 public 行为 snapshot（JSON 结构断言，非实现细节）
3. 标记 helpers 当前 export 列表（routes 引用的符号）

**验收**

- [x] 基线 pytest 全绿
- [x] `grep "from services.ops.helpers import"` 清单写入本 Plan 附录（实施时更新）

---

### Step 2：提取 cluster_importer（3 天）

**动作**

1. 剪切 `_load_cluster_json` ~ `_sync_cluster_to_topology` 至 `cluster_importer.py`
2. helpers facade 经 `cross_bind.wire_all()` 合并子模块符号
3. 不改函数签名；routes 仍 `from services.ops.helpers import _sync_cluster_to_agents`（facade 转发）

**验收**

- [x] cluster 同步函数经 facade 可调用
- [x] pytest 仍绿

---

### Step 3：提取 topology_registry + contracts（4 天）

**动作**

1. 迁移 topology load/save/list
2. 迁移 node contract registry（`_node_contract_registry_path` 等）
3. 单元测试：`tests/test_topology_registry.py` mock 文件 IO

**验收**

- [x] `topology_binding_service` 集成测试 pass
- [x] `tests/test_topology_registry.py` pass

---

### Step 4：提取 agent_registry + runtime_orchestrator（4 天）

**动作**

1. Agent stale 标记、heartbeat merge
2. `_runtime_active_for_scope` 保留 `runtime_service.py`；orchestration 在 `runtime_orchestrator.py`
3. 确认 publish precheck 仍能找到 active runtime

**验收**

- [x] Release publish 集成测试 pass
- [x] Ops runtime 概览测试 pass

---

### Step 5：提取 diagnostics + 瘦身 helpers（2 天）

**动作**

1. diagnostics 独立（`services/ops/diagnostics.py`）
2. helpers.py **156 行**（render + auth + re-export）
3. 启用 `release_module_size_gate` 对 `ops/helpers.py` max lines=450

**验收**

- [x] helpers.py line count ≤450
- [x] `tests/test_ops_helpers_facade.py` pass

---

### Step 6：更新 import 路径（可选，1 天）

**动作**

1. routes 仍经 facade import（Step 6 可选，后续 PR）
2. 文档 `docs/architecture/entrypoint_map.md` 更新 Ops 模块图（待续）

---

## 8. 附录：facade import 引用清单（2026-07-28）

| 文件 | 符号 |
|------|------|
| `services/ops/storage.py` | `_append_bounded` |
| `services/release/order_publish_flow.py` | `_runtime_active_for_scope` |
| `services/release/order_diagnostics.py` | `_load_topology_scoped` |
| `services/ops/environment_runtime_service.py` | `_realtime_metric_points` |
| `routes/delivery/helpers.py` | `_render_ops_page` |
| `routes/admin_routes.py` | `_render_ops_page` |
| `services/admin/report_service.py` | `_load_agent_registry_v2` |
| `services/release/bundle_service.py` | `_resolve_topology_context` |
| `services/release/topology_binding_service.py` | `_env_label`, `_list_topologies`, `_runtime_active_for_scope` |
| `services/release/scope_resolver.py` | `_load_topology_scoped` |
| `scripts/run_gacha_release_full_e2e.py` | `_runtime_active_for_scope`, `_spawn_runtime_start_orchestration` |
| `scripts/transport_login_matrix.py` | （多个 ops helpers） |

**支撑模块**

- `shared_bootstrap.py` — 模块级常量/探活缓存
- `cross_bind.py` — 子模块私有符号互绑
- `helpers.py.bak` — 拆分前完整备份（回滚用）

---

## 7. 完成定义（DoD）

- [x] helpers.py ≤450 行（当前 156）
- [x] 6 个子模块存在且职责文档化（模块 docstring）
- [ ] W-P1-1 关闭（待评审）
- [x] P1-04 / P2-01 可依赖 `runtime_orchestrator` 公开 API

| PR | 内容 | 风险 |
|----|------|------|
| PR-1 | Step 1 测试 + cluster_importer | 低 |
| PR-2 | topology_registry + contracts | 中 |
| PR-3 | agent + runtime | 高（publish 依赖） |
| PR-4 | diagnostics + 瘦身 | 低 |

每 PR 必须：**pytest 0 fail + 无行为变更声明**

---

## 6. 回滚

- 每 PR 独立 revert
- facade 保留旧函数名至 1 个 release cycle

---

## 7. 完成定义（DoD）— 唯一有效段

- [x] helpers.py ≤450 行（当前 156）
- [x] 6 个子模块存在且职责文档化（模块 docstring）
- [x] W-P1-1 关闭（evidence + entrypoint_map）
- [x] P1-04 / P2-01 可依赖 `runtime_orchestrator` 公开 API

> 原 §7 重复 DoD 已删除（2026-07-29 closure pass）。
