# P18 环境详情

## 布局（1680×960）

| 区域 | 占比 | 说明 |
|------|------|------|
| 页头 | 全宽 | 返回 + 标题 24px + 说明 14px + 右侧操作 |
| 主栏 | ~76% | 交付线矩阵 + 进行中发布单 |
| 右栏 | 300px | 交付范围 / 平台 / 初始化 / 配置入口 |

**无 KPI 摘要行** — 页头下方直接进入双栏内容。

## 排版 token

| 用途 | 字号 | 颜色 |
|------|------|------|
| 页面标题 | 24/32 600 | #1d2939 |
| 说明/正文 | 14/22 | #475467 |
| 分区标题 | 16/24 600 | #1d2939 |
| 字段标签 | 12/18 500 | #667085 |
| 字段值 | 14/22 500 | #1d2939 |
| 拓扑等宽 | 13/20 | #475467 |

## 交付线平台卡片（2026-07-20 · 拓扑绑定整合）

> 架构规格：[`topology_binding_architecture.md`](topology_binding_architecture.md)  
> 绑定入口：**唯一** — 卡片服务端页签「拓扑」→ 抽屉（非侧栏/独立页）

### 布局

- 按渠道分组；组内 **`repeat(auto-fill, minmax(260px, 320px))`** 多列卡片
- 单卡 max-width **320px**；无 min-height 撑高

### 结构

```
┌─ 平台图标 + 名称 + 状态徽章 ─────────────┐
│ status hint（ellipsis）                    │
│ 版本 / Bundle / 拓扑（名称 + 来源两行）     │
│ [版本] 独立全宽按钮                         │
│ ┌ 客户端 │ 服务端 ┐ 页签                   │
│ │ 构建 发版 │ 拓扑 GM 测试 │               │
└────────────────────────────────────────────┘
```

| 区域 | 控件 | 行为 |
|------|------|------|
| 头 | 平台图标 **44×44**（SVG 26×26）+ 名称 + 状态徽章 | — |
| 字段 | 版本 / Bundle / 拓扑 | 拓扑显示 **名称 + 来源 badge** |
| 版本行 | **版本** 按钮 | `/versions` scoped |
| 客户端页签 | 构建 / 发版 | channel build / release journey |
| 服务端页签 | 拓扑 / GM / 测试 | 抽屉 / `/actions` / `/diagnostics` |

### 状态色

| 状态 | 卡片 | 图标底 | hint |
|------|------|--------|------|
| 已配置 | 浅绿渐变 + 绿边框/左线 | `#e8f8e8` | `#389e0d` |
| 未配置 | 浅橙渐变 + 橙边框/左线 | `#fff7e6` | `#d48806` |

### 按钮语义色

| 按钮 | class | 用途 |
|------|-------|------|
| 构建 | `.matrix-btn.build` | 蓝底（未配置卡橙底） |
| 发版 | `.matrix-btn.release` | 绿底 |
| 版本 | `.matrix-btn.version` | 中性 |
| 拓扑 | `.matrix-btn.topology` | 紫系 `#531dab` |
| GM | `.matrix-btn.server-gm` | 橙系 |
| 测试 | `.matrix-btn.server-test` | 蓝系 |

## 拓扑绑定抽屉

### 布局

- 固定右侧 `560px` 面板 + 遮罩
- Scope 只读条 + 当前命中
- 筛选：搜索 / 环境 / 状态 / 「优先本环境」
- 可滚动拓扑卡片列表
- 底部：保存 / 清除覆盖 / 打开拓扑资产

### 拓扑卡片必显

- 状态 badge、已绑定(N)、★ 当前命中
- 名称、环境、节点/连线、Runtime 活跃
- 绑定引用 scope 列表
- 「选为绑定目标」「画布」

### 深链

`/admin/projects/{id}/environments/{env}?open_topology_drawer=1&env_key=&channel_id=&platform=`

兼容 `/topology-bindings?...` → 302 至上述 URL。

## 验收清单

| # | 项 | PASS/FAIL |
|---|-----|-----------|
| 1 | 无 KPI 摘要区 | |
| 2 | 卡片网格 260–320px（非 200–220 窄卡） | |
| 3 | 版本独立按钮 + 客户端/服务端页签 | |
| 4 | 拓扑字段显示名称+来源（非裸 topology_id） | |
| 5 | 服务端「拓扑」打开抽屉（非跳转独立页） | |
| 6 | 侧栏/右栏无「拓扑绑定」入口 | |
| 7 | 抽屉列表含 status/runtime/binding_refs | |
| 8 | 保存绑定后卡片拓扑回显更新 | |
| 9 | Android/iOS 同渠道可不同拓扑 | |
| 10 | 静态 cache `20260720-topology-binding-v1` 已加载 | |

## 实现文件

| 文件 | 职责 |
|------|------|
| `project_environment_detail.html` | 抽屉 DOM |
| `project_environment_detail.css` | 卡片 + 抽屉样式 |
| `project_delivery.js` | `renderDeliveryMatrixHtml` |
| `topology_binding_drawer.js` | 抽屉交互 |
| `project_delivery.py` | 脚本注入 + cache bump |
