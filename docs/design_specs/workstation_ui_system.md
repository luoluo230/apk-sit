# 管理端整站 UI 规范（Work Station）

真源色板与壳层见 [admin_console_shell.md](./admin_console_shell.md)。  
本文件规定：**所有可上线管理页**必须如何组页，禁止再按页发明一套 Tailwind demo 皮肤。

## 1. 产品分层

| 层 | 页面角色 | 导航 |
|---|---|---|
| 工作室 | 跨项目：工作台、消息、项目列表、成员、打包机、站点外壳、文档中心、审批、我的任务 | 侧栏「工作室」+ 顶栏 |
| 项目内 | 总览 / 发版 / 游戏服 / 休闲服务 / 协作 / 设置 | 选中项目后侧栏展开 |
| 玩家站 / 论坛 | 不走本规范 | 各自壳 |

工作台 = 工作室首页：回答「现在要我干什么」+「高频去哪」+「最近项目」，**不是**全站磁贴墙，也**不是**只有待办列表。

## 2. 视觉与组件（强制复用）

| 用途 | 类 / 文件 | 禁止 |
|---|---|---|
| Token | `design-tokens.css` | 页内写死 indigo/purple 新色板 |
| 壳 | `ops_shell.html` + `ops_shell.css` | 自建 `DOCTYPE` + `tailwind.css` + Font Awesome CDN |
| 页头 | `pm-page-head` / `pm-page-head-actions` | 渐变条标题 + emoji 按钮 |
| 按钮 | `pm-btn` / `pm-btn--primary` / `--danger` / `--compact` | `bg-indigo-600 rounded-xl` 散装按钮 |
| 筛选 | `pm-filter-bar` | 无边框一排裸 `input/select` |
| 表格 | `pm-table-panel` + `pm-table` | 未套面板的裸 table |
| KPI | `pm-kpi-row` + `pm-kpi-card`（≤4～5 个） | 装饰性全 0 的 8 宫格模块墙 |
| 弹层表单 | `pm-modal` | 列表中间突然插入的裸表单 |
| 空态 | `studio-empty` 或 `pm-placeholder-page`：说明原因 + 主操作 | 仅「暂无 xxx」无下一步 |
| 标签 | `pm-tag` / `pm-tag--*` | 各页自造 badge 色 |

工作室遗留页可暂挂 `studio-pages.css` 工具 shim，**新改版页不得依赖 Tailwind 类名作为主样式**。

## 3. 页面骨架（所有列表/工作页）

```
pm-page-head          标题 + 一句说明 + 主/次操作
[可选] pm-kpi-row     仅真实可解释指标；全 0 且无动作时不要堆
pm-filter-bar         搜索 + ≤4 个筛选 + 重置
主内容                pm-table-panel 或卡片列表
空/错/载              统一文案与主按钮
```

创建/编辑：**模态或右侧抽屉**，不要撑开列表中间。

## 4. 工作台信息架构（已定稿）

1. **待我处理**（分组）：待审批 / 我的任务（进行中+逾期）/ 未读通知 / 发版风险（缺包等）  
2. **快捷入口**（固定约 6 个）：项目列表、我的任务、审批中心、消息、打包机、发版（无项目时进项目列表并提示）  
3. **最近项目**：收藏优先，其次可见项目；点进项目总览并带 `env_key`

不放：成员、站点外壳、审计、GM、诊断（侧栏即可）。

## 5. Demo 页盘点与改造波次

判定：自建 HTML 壳 / 仍引 Tailwind·CDN / 裸表单 / 与侧栏两套导航 → **必须改**。  
**产品级结案不以「已进壳」为准**，以 [product_ui_scorecard.md](../qa/product_ui_scorecard.md) 八维 PASS 为准。

| 波次 | 页面 | 路径 | 问题 | 状态 |
|---|---|---|---|---|
| F0 | 全站地基 | `product_polish.css` + 侧栏折叠 | 密度/空态/标签/对比度 | 进行中 |
| W1 | 工作台 | `/admin` | 待办缺类型标签 | 已加「待审/缺包」等 tag |
| W1 | 成员 | `/admin/users` | 操作列挤、角色裸字 | 角色 tag + 短操作文案 |
| W1 | 项目任务 | `.../tasks` | emoji 星、Tailwind 弹层 | 紧急度改为数字按钮；弹层继续收 |
| W1 | 站点外壳 | `/admin/site-config` | Tailwind 表单 | FAIL → 改造中 |
| W2 | 总览 / 运行 / 动作 / 构建产物 | 项目内 | 空「—」骨架感 | 进行中 |
| 例外 | 官网可视化编辑器 | `/admin/site-config/editor/*` | 全屏画布 | 保留独立壳 |
| 遗留 FAIL | 旧 dashboard / products 模板 | 仍引 Tailwind+FA | 迁壳或下线入口 | 待办 |

玩家站、登录页、论坛不在本波次。

## 6. 实现约束

- 路由仍薄；页面 HTML 可放 `views/`，样式进 `project_ui/`，禁止塞回 `helpers.py` / `admin_routes.py` 巨石。
- 不改业务 API 语义与权限；只换壳与交互承载。
- 每波：改过的 py `py_compile`，改过的 js `node --check`，浏览器点主路径。
- 完成定义：该页在 `ops_shell` 内、无 tailwind/cdnjs、空态有主操作、主按钮可用。

## 7. 与历史计划关系

[P3-01](../architecture/plans/P3-01_workstation_convergence.md) 把工作台收成待办是收敛导航用的；**商业可用工作台以本规范 §4 为准**，允许在待办之上加快捷入口与最近项目。
