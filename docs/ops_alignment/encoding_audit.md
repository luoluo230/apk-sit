# 全局中文编码治理审计（第一轮）

日期：2026-06-01  
范围：运维 Agent 管控链路（页面 + 后端响应）

## 已修复
- 修复 `ops_platform_agent_control.js` 中错误分隔符与乱码片段，清理损坏文本拼接。
- 修复 Agent 卡片与设备组标题行文案：统一中文 UTF-8。
- 修复后端 `/api/ops-platform/agents` 指标覆盖逻辑，避免设备快照覆盖单 Agent 实时指标，防止“看起来乱码/异常跳变”误判。
- **2026-06-09**：Ops 路由拆分后修复 `routes/ops/pages.py` 运维平台标题乱码（「运维平台」）。
- **2026-06-09**：`ops_topology_workbench.html` + `static/ops/workbench/*.js` UTF-8 常量审计通过（无可见 mojibake）。
- **2026-06-09**：Classic GM 内嵌 HTML 随 `routes/ops/legacy_gm.py` 隔离；Ops 主推页面模板无新增乱码。

- **2026-06-09（第二轮）**：删除 `routes/ops/legacy_gm.py`、`routes/ops/pages.py` 中 unreachable 的旧版内嵌 HTML（GBK 乱码源）；修复 `overview.py`、`business_test.py`、`helpers.py` 中仍会被 API 返回的中文文案。
- **2026-06-09**：`release_bundles` 打包排除 `*.rdb`（Redis 二进制快照，非文本乱码）。

## 仍待处理（低优先级）
- `routes/docs_routes.py`、Jenkins `config.xml` 等历史模块仍有 GBK 乱码，不在本轮 Ops 主推路径内。

## 验证
- `py -3 -m py_compile portals/common/core/routes/ops/*.py portals/common/core/services/ops/*.py` 通过。
- `node --check portals/common/core/static/ops/workbench/state.js`（及同目录分包）通过。
- 页面资源版本：`ops_topology_workbench.html` → `?v=20260609-admin-modular-v1`。
- 回归：`py -3 dev/tools/run_admin_regression_gate.py --strict --skip-live`。
