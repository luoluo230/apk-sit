# Admin Ops 模块边界说明

更新时间：2026-06-09  
范围：仅 `APP_PORTAL_MODE=admin` 管理端 Ops 平台

## 包结构

```
portals/common/core/
├── routes/gm_legacy.py          # 兼容 shim：re-export routes.ops.bp
├── routes/ops/                  # HTTP 路由（按域拆分）
│   ├── pages.py                 # /admin/ops-platform/* 页面
│   ├── overview.py              # 概览、事件、变更治理摘要
│   ├── agents.py                # Agent 管控 API + SSE
│   ├── services.py              # 服务器运维 services/action
│   ├── topology.py              # 拓扑 CRUD、蓝图、绑定
│   ├── runtime.py               # flow-control / flow-status
│   ├── actions.py               # 动作执行、flow-smoke、stress-test
│   ├── business_test.py         # 业务测试 catalog/run
│   ├── cluster.py               # cluster/sync、deployment-catalog
│   └── legacy_gm.py             # /admin/gm-classic、/api/gm-legacy/*
└── services/ops/
    ├── constants.py             # OPS_* 键、ops_gateway 单例
    ├── storage.py               # JSON 持久化读写
    ├── encoding.py              # 乱码检测/修复
    └── helpers.py               # 业务逻辑（classic GM + Ops 共享 helper）
```

## 职责边界

| 层 | 职责 | 禁止 |
|----|------|------|
| `routes/ops/*` | HTTP 校验、参数解析、`jsonify`、审计日志 | 直接持久化、复杂业务分支 |
| `services/ops/storage.py` | `_load_*` / `_save_*` JSON 配置 | 注册 Flask 路由 |
| `services/ops/helpers.py` | 拓扑/Agent/Runtime 业务、classic GM | `import routes.*` |
| `routes/gm_legacy.py` | Blueprint 名与 URL 兼容 re-export | 新业务逻辑 |
| `static/ops/workbench/*.js` | 拓扑工作台 UI（按 IIFE 顺序加载） | 修改玩家端/论坛静态资源 |

## 与 gm_ops / legacy_gm 的关系

- **Ops 平台**（导航主推）：`routes/ops/*` + `services/ops/*`，Blueprint 名仍为 `gm_legacy`（零 URL 变更）。
- **Classic GM**（隔离）：`routes/ops/legacy_gm.py`，便于后续下线，默认不在 Ops 导航主推。
- **权限模块**：页面与 API 仍使用 `@admin_required("gm_ops")`。

## 前端分包

| 文件 | 职责 |
|------|------|
| `static/ops_platform_api.js` | 全局 `OpsApi` fetch 封装 |
| `static/ops/workbench/state.js` | 常量、state、模式/布局 helper（IIFE 首段） |
| `static/ops/workbench/runtime.js` | 运行态、业务测试、Agent 刷新 |
| `static/ops/workbench/canvas.js` | 画布渲染、坐标、连线 |
| `static/ops/workbench/nodes.js` | 节点/预设/检查器 |
| `static/ops/workbench/api.js` | 拓扑加载、蓝图、生命周期 |
| `static/ops/workbench/index.js` | 事件绑定、`boot()`（IIFE 末段） |

## 回归门禁

```bash
py -3 dev/tools/run_admin_regression_gate.py --strict --skip-live
```

详见 [`docs/ops_alignment/09_admin_regression_gate.md`](../../../docs/ops_alignment/09_admin_regression_gate.md)。

## Admin-only 发布包

```bash
cd portals/common/core
py scripts/build_split_deploy_bundles.py --profile admin
```

产物：`release_bundles/admin-only/`，含 `manifest.json`、4 个 ops agent 工具脚本、`portals/intranet` + `portals/common/core`（不含 tests/docs/.cursor）。
