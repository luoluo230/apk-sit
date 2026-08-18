# 服务器管理 Hub — 设计规格

## 真源

| 项 | 值 |
|---|---|
| 全局 URL | `/admin/server-management` |
| 项目 URL | `/admin/projects/{project_id}/server-management` |
| Tab | `topology`（中重度拓扑）\| `baas`（轻度 BaaS） |
| 模板 | `server_management_hub.html` |
| 样式 | `server_management_hub.css` + `project_environment_detail.css`（env-line-card） |
| 脚本 | `server_management_hub.js` |
| BFF API | `/api/server-management/topologies` \| `/api/server-management/baas-services` |

## 页面结构

1. 页头：标题「服务器管理」+ 新建按钮（随 Tab 变化）
2. Tab 切换：中重度服务器 \| 轻度服务器
3. 筛选条：搜索（名称/ID）、项目、环境、状态、刷新
4. 卡片网格：响应式 3 列（≥1200px）→ 2 列 → 1 列
5. 空态 / 加载态 / 错误态

## 统一卡片布局

| 区域 | 字段 |
|------|------|
| 头部 | 图标、名称、状态 Badge |
| 元信息 | 唯一 ID（可复制）、描述摘要（2 行截断） |
| 绑定 | 项目名 + 项目图、环境、平台/渠道 chips |
| 运行 | 状态文案、持续时长、报错标记 |
| 统计 | 拓扑：节点/连线；BaaS：配置版本/玩家数 |
| 日志 | 最近 2–3 条 warn/error 摘要 |
| 操作 | 编辑、禁用/启用、删除、深链 |

## 状态 → 卡片色

| 状态 | class | 色 |
|------|-------|-----|
| running / active / validated | `configured` | 绿 |
| draft / stopped / idle | `unconfigured` | 黄 |
| error / failed / degraded | `error` | 红 |
| disabled / archived | `neutral` | 灰 |

## Modal 规则

**创建**：名称（必填）、唯一 ID（slug `[a-z0-9][a-z0-9_-]{2,63}`）、描述、图标 URL、环境、项目（全局页可选）

**编辑**：名称、ID readonly；可改描述、图标、其他非标识字段

## 11 维 UI checklist

| # | 维度 | 要求 |
|---|------|------|
| 1 | 布局 | Tab + 筛选 + 卡片网格 |
| 2 | 间距 | 12px 卡片 gap，16px 面板 padding |
| 3 | 字体 | design-tokens 默认栈 |
| 4 | 字号 | 标题 18px，卡片名 14px，元信息 12px |
| 5 | 对齐 | 卡片内左对齐，Badge 右对齐 |
| 6 | 颜色 | 状态语义色见上表 |
| 7 | 图标 | nav_topology / nav_project_setting 默认 |
| 8 | 响应式 | 3/2/1 列断点 |
| 9 | 交互 | hover 阴影、disabled 按钮灰化 |
| 10 | 反馈 | toast/inline 错误、confirm 删除 |
| 11 | 文案 | 中文，无乱码 |

## 验收清单

| ID | 项 | 结果 |
|---|---|---|
| S01 | 全局 + 项目双入口同一组件 | PASS (routes + template) |
| S02 | Tab 切换 + URL query 同步 | PASS (JS) |
| S03 | 创建自定义 ID + 重复 409 | PASS (unit test) |
| S04 | 编辑时 name/id 不可变 | PASS (unit test) |
| S05 | 禁用/删除 guard | PASS (unit test + API) |
| S06 | 卡片状态色正确 | PASS (CSS classes) |
| S07 | 深链画布/配置/GM | PASS (card actions) |
