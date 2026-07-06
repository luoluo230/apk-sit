# P16 环境运行概览 — A0 建档与 MVP-A 验收

## 真源

| 项 | 值 |
|---|---|
| 设计图 | `docs/design_assets/project_management/P16_environment_runtime_overview.png` |
| 基准视口 | 1680 × 960 |
| Canonical URL | `/admin/projects/{project_id}/environments/{env_key}/runtime` |
| 总览 nav 深态 | `/admin/projects/{id}/overview/runtime?env_key=` → redirect canonical |
| BFF API | `GET /api/projects/{id}/environments/{env_key}/runtime-overview` |
| 模板 | `project_environment_runtime.html` |
| 样式 | `project_environment_runtime.css` + `pm-filter-bar` + `pm-kpi` + `pm-table` + `pm-right-rail` |
| 脚本 | `project_environment_runtime.js` |

## MVP-A 范围

| 模块 | MVP-A | Phase 2 |
|---|---|---|
| 四维筛选 + 刷新 | PASS | — |
| KPI 五卡 | PASS | 较昨日趋势 |
| 服务实例表 | PASS | — |
| 右侧告警摘要 | PASS | — |
| 右侧当前阻断 | PASS | — |
| 右侧快速操作 | PASS | — |
| 环形图 / sparkline | — | Phase 2 |
| 值班 / 变更 / 风险 | — | Phase 2 |

## 与 P02 / 环境管理边界

- **P02** `/overview`：多环境交付摘要卡
- **P16** `/environments/{env}/runtime`：单环境 ops 运行态（必须锁定 env_key）
- **环境配置** `/overview?tab=environments`：环境 CRUD + 交付范围

## 数据质量

- 有 `gm_ops` 权限且 agent 在线：展示 live KPI
- 无 ops 权限或 probe 缺失：`data_quality.metrics_missing=true`，禁止伪造 live 曲线

## 验收清单（MVP-A）

| ID | 项 | 结果 |
|---|---|---|
| R01 | KPI 来自 ops 或显式 missing | PASS (BFF + unit test) |
| R02 | 服务表操作链到 agents/diagnostics | PASS |
| R03 | 阻断合并 delivery + runtime | PASS |
| R04 | 侧栏「运行概览」→ runtime 深态 | PASS |
| R05 | P02/P03「进入运行工作台」入口 | PASS |
