# 全局中文编码治理审计（第一轮）

日期：2026-06-01
范围：运维 Agent 管控链路（页面 + 后端响应）

## 已修复
- 修复 `ops_platform_agent_control.js` 中错误分隔符与乱码片段，清理损坏文本拼接。
- 修复 Agent 卡片与设备组标题行文案：统一中文 UTF-8。
- 修复后端 `/api/ops-platform/agents` 指标覆盖逻辑，避免设备快照覆盖单 Agent 实时指标，防止“看起来乱码/异常跳变”误判。

## 仍待处理（下一轮）
- `gm_legacy.py` 早期页面（经典GM/旧版ops整页内嵌HTML）仍存在历史乱码，需要分模块拆分并逐页修复。
- `ops_topology_workbench.html` 与 `ops_platform_workbench.js` 需做同样的中文常量检查。

## 验证
- `py -3 -m py_compile portals/common/core/routes/gm_legacy.py` 通过。
- `node --check portals/common/core/static/ops_platform_agent_control.js` 通过。
- 页面资源版本已升级：`ops_agent_control_page.html` -> `?v=20260601b`。
