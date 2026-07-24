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

- [ ] 基线 pytest 全绿
- [ ] `grep "from services.ops.helpers import"` 清单写入本 Plan 附录（实施时更新）

---

### Step 2：提取 cluster_importer（3 天）

**动作**

1. 剪切 `_load_cluster_json` ~ `_sync_cluster_to_topology` 至 `cluster_importer.py`
2. helpers 改为 `from services.ops.cluster_importer import sync_cluster_to_agents`
3. 不改函数签名；routes 仍 `from services.ops.helpers import _sync_cluster_to_agents`（facade 转发）

**验收**

- [ ] cluster 同步行为不变（手动：改 cluster.json port → sync → Agent 页可见）
- [ ] pytest 仍绿

---

### Step 3：提取 topology_registry + contracts（4 天）

**动作**

1. 迁移 topology load/save/list
2. 迁移 node contract registry（`_node_contract_registry_path` 等）
3. 单元测试：`tests/test_topology_registry.py` mock 文件 IO

**验收**

- [ ] 拓扑编辑器保存/加载无回归
- [ ] `topology_binding_service` 集成测试 pass

---

### Step 4：提取 agent_registry + runtime_orchestrator（4 天）

**动作**

1. Agent stale 标记、heartbeat merge
2. `_runtime_active_for_scope` → runtime_orchestrator（**order_publish_flow 依赖此函数**）
3. 确认 publish precheck 仍能找到 active runtime

**验收**

- [ ] Release publish 集成测试 pass
- [ ] Ops runtime 启停 UI 可用

---

### Step 5：提取 diagnostics + 瘦身 helpers（2 天）

**动作**

1. diagnostics 独立
2. helpers.py **目标 ≤400 行**（仅 render + auth + re-export）
3. 启用 `release_module_size_gate` 对 `ops/helpers.py` max lines=450

**验收**

- [ ] helpers.py line count ≤450
- [ ] 全量 pytest portals/common/core

---

### Step 6：更新 import 路径（可选，1 天）

**动作**

1. routes 逐步改为直接 import 子模块（非必须，降低 facade 层）
2. 文档 `docs/architecture/entrypoint_map.md` 更新 Ops 模块图

---

## 5. PR 策略

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

## 7. 完成定义（DoD）

- [ ] helpers.py ≤450 行
- [ ] 6 个子模块存在且职责文档化（模块 docstring）
- [ ] W-P1-1 关闭
- [ ] P1-04 / P2-01 可依赖 `runtime_orchestrator` 公开 API
