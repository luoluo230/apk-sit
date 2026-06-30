# P01 项目列表 — A0 建档与验收

## 真源

| 项 | 值 |
|---|---|
| 设计图 | `docs/design_assets/project_management/P01_project_list_10_54_37.png`（源：`D:\Art\设计图\设计图\ChatGPT Image 2026年6月13日 10_54_37 (1).png`） |
| 基准视口 | 1680 × 960 |
| 运行 URL | `http://127.0.0.1:5003/admin/projects` |
| 模板 | `portals/common/core/templates/project_list.html` |
| 样式 | `project_list.css` + `project_ui/pm-project-card.css` + `project_ui/pm-right-rail.css` |
| 脚本 | `project_list.js` + `project_ui/pm-display-labels.js` |
| Cache 版本 | `20260625-pm14` |

## A0 行级清单（37.png → 实现对照）

每行验收结果：`PASS` / `FAIL` / `N/A`

### 页面标题区

| ID | 设计元素 | 设计规格 | 实现位置 | 结果 |
|---|---|---|---|---|
| H01 | 收藏星标 | 标题左侧 36×36 描边按钮 | `pm-page-star` + `pm-shell.css` | PASS |
| H02 | 标题 | 「项目列表」24px/600 | `.p01-head h1` | PASS |
| H03 | 副标题 | 「共 N 个项目」13px 灰色 | `#p01TotalCount` | PASS |
| H04 | 主操作 | 右侧蓝色「+ 创建项目」 | `#p01CreateBtn` | PASS |

### 筛选条（单行）

| ID | 设计元素 | 设计规格 | 实现位置 | 结果 |
|---|---|---|---|---|
| F01 | 布局 | 单行：搜索 + 3 下拉 + 右侧图标视图切换 | `.p01-filters` nowrap override | PASS |
| F02 | 搜索 placeholder | 「搜索项目名称、负责人、描述、标签…」 | `#p01Search` | PASS |
| F03 | 状态下拉 | 「状态：全部」 | `#p01FilterStatus` | PASS |
| F04 | 负责人下拉 | 「负责人：全部」 | `#p01FilterOwner` | PASS |
| F05 | 健康状态下拉 | 「健康状态：全部」 | `#p01FilterHealth` | PASS |
| F06 | 视图切换 | 仅图标（卡片/表格），无文字 | `.p01-view-toggle` | PASS |

### 主布局（左网格 + 右 280px）

| ID | 设计元素 | 设计规格 | 实现位置 | 结果 |
|---|---|---|---|---|
| L01 | 左区占比 | 三列卡片网格，gap 16px | `.p01-card-grid` | PASS（1680 宽） |
| L02 | 右栏宽度 | 280px sticky | `.pm-page-rail` | PASS |
| L03 | 分页位置 | 卡片网格下方，左对齐「共 N 条」 | `#p01Pagination` | PASS |

### 项目卡片（单卡 12 子元素）

| ID | 设计元素 | 设计规格 | 实现位置 | 结果 |
|---|---|---|---|---|
| C01 | 项目图标 | 40×40 圆角 8px | `.pm-project-card__icon` | PASS |
| C02 | 项目名称 | 15px/600 单行省略 | `.pm-project-card__title h3` | PASS |
| C03 | 状态 Tag | 带色点 pill：运行中/风险中/阻塞中/已归档 | `.pm-project-card__status` | PASS |
| C04 | 卡片星标 | 标题行右侧空心星 | `.pm-project-card__star` | PASS |
| C05 | 卡片 ⋯ | 标题行 vertical more | `.pm-project-card__more` | PASS |
| C06 | 负责人行 | 头像 + 姓名 + 右「最后更新: HH:mm」 | `.pm-project-card__owner` | PASS |
| C07 | KPI 环境健康 | 圆底图标 + % + 副文案（良好/风险/阻塞） | `[data-metric=health]` | PASS |
| C08 | KPI 生产版本 | 圆底蓝 + 版本号 | `[data-metric=version]` | PASS |
| C09 | KPI 待审批 | 圆底橙 + 数字 | `[data-metric=pending]` | PASS |
| C10 | KPI 阻塞项 | 圆底红 + 数字 | `[data-metric=blockers]` | PASS |
| C11 | 最新发布 | 版本 + 日期时间 + 人读状态 Tag | `.pm-project-card__release` | PASS |
| C12 | 页脚 | 居中「进入项目总览 →」+ 右下 ⋯ | `.pm-project-card__foot` | PASS |

### 归档态卡片

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| A01 | 整卡灰化 | opacity/背景 #fafbfc | N/A（当前环境无已归档项目样本） |
| A02 | Tag | 「已归档」灰色 | PASS（CSS/逻辑已实现，待有样本复验） |
| A03 | 指标 | 四格均为 — | PASS（逻辑已实现，待有样本复验） |

### 右栏

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| R01 | 筛选空态 | 有筛选且无结果时：chips + 插画 + 重置 | PASS |
| R02 | 无筛选时 | 仅「快速操作」三块（无渠道管理） | PASS |
| R03 | 快速操作 1 | 创建新项目 / 从模板创建项目 | PASS |
| R04 | 快速操作 2 | 批量导入项目 / 从 CSV 导入 | PASS |
| R05 | 快速操作 3 | 项目归档管理 / 查看已归档项目 | PASS |

### 分页

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| P01 | 总条数 | 「共 N 条」 | PASS |
| P02 | 条/页 | 下拉 12 条/页 | PASS |
| P03 | 页码 | 上一页 / 数字 / 下一页 | PASS |
| P04 | 跳页 | 「跳至 [ ] 页」 | PASS |

## 1680×960 屏级 PASS 表（2026-06-30，pm13 复验）

| 区域 | PASS | FAIL | N/A | 备注 |
|---|---|---|---|---|
| 全局壳层（侧栏/顶栏/面包屑） | 2 | 5 | 0 | 232/72 OK；侧栏 IA/用户部门/背景渐变仍 FAIL（独立任务） |
| 标题区 H01–H04 | 4 | 0 | 0 | |
| 筛选条 F01–F06 | 6 | 0 | 0 | |
| 主布局 L01–L03 | 3 | 0 | 0 | |
| 项目卡片 C01–C12 | 12 | 0 | 0 | `pmProjectCardTemplate` + `pm-project-card.css` |
| 归档态 A01–A03 | 2 | 0 | 1 | 无归档样本 |
| 右栏 R01–R05 | 5 | 0 | 0 | 已移除「渠道管理」 |
| 分页 P01–P04 | 4 | 0 | 0 | |
| **P01 内页合计** | **38** | **0** | **1** | **壳层 5 FAIL 不阻塞 P01 内页项** |

**禁止宣称「全站 1:1 完成」** — 壳层与设计仍有差距；P01 内页 A0 项除 A01 样本缺失外均已 PASS。

### 浏览器验收记录

- 视口：1680×960（cursor-ide-browser）
- 登录：admin（session 已存在）
- 加载 CSS：`project_list.css?v=20260625-pm13`，`pm-project-card.css?v=20260625-pm13`，`pm-right-rail.css?v=20260625-pm13`
- 加载 JS：`pm-display-labels.js?v=20260625-pm13`，`project_list.js?v=20260625-pm13`
- 截图归档：`docs/evidence/2026-06-30/p01-project-list-1680.png`
- 目检要点：色点 Tag「阻塞中」、圆底 KPI + 副文案「阻塞」、发布 Tag「部分成功」（非 `artifacts_ready`）、卡片星标 + 页脚 ⋯、右栏仅 3 项快速操作

### 已点击验证（交互）

| 操作 | 结果 |
|---|---|
| 卡片 ⋯ 菜单 | PASS — 出现进入总览/编辑/删除/归档 |
| 快速操作「项目归档管理」 | PASS — 状态下拉切至「已归档」并 reload |
| 「+ 创建项目」 | 未在本轮点击（弹窗 DOM 存在，历史回归 PASS） |

## 共享组件契约（pm13）

| 组件 | 固定结构 | JS 职责 |
|---|---|---|
| 项目卡 | `<template id="pmProjectCardTemplate">` | `fillProjectCard()` 只填文本/class/href，不改 DOM 结构 |
| 状态文案 | `pm-display-labels.js` | `releaseStatus` / `cardStatus` / `healthSublabel` |
| 右栏 | `pm-right-rail.css` + `.p01-rail-panel` | 显示/隐藏筛选空态 |

## 回归矩阵（功能与视觉分离）

| 功能 | API/路由 | 视觉项 | 功能 | 视觉 |
|---|---|---|---|---|
| 列表加载 | `GET /admin/projects/list` | 卡片/grid 渲染 | PASS | PASS |
| 搜索/筛选 | 前端 filter | 筛选条单行 | PASS | PASS |
| 分页 | 前端 paginate | 底部分页器 | PASS | PASS |
| 创建项目 | `POST /admin/projects/create` | 弹窗字段完整 | PASS | PASS |
| 编辑项目 | `POST /admin/projects/update` | 含域名/Git SSH | PASS | PASS |
| Git 验证 | `POST /api/jenkins-manage/validate-git` | 按钮+结果文案 | PASS | PASS |
| 删除项目 | `DELETE /admin/projects/delete/{id}` | 卡片 ⋯ 菜单 | PASS | PASS |
| 归档/取消归档 | `POST .../archive` | 菜单项 | PASS | PASS |
| 渠道管理 | `/admin/channels` | 不在设计快速操作内 | PASS（入口在别处） | PASS |
| 进入总览 | `/admin/projects/{id}/overview` | 页脚链接 | PASS | PASS |
| 批量导入 | — | 诚实提示未开放 | N/A | PASS |
| 状态文案 | — | 禁止裸 API status | PASS | PASS — 「部分成功」等 |

## 图标映射（2026-06-30 pm14 修正）

| 区域 | 设计语义 | 错误用法（pm13） | 正确资源 |
|---|---|---|---|
| KPI 待审批 | 橙色文档+勾选 | `status_pending`（灰色时钟） | `kpi_change.svg` |
| KPI 阻塞项 | 红色盾牌+叉 | `status_error`（圆环叉） | `card_kpi_blockers.svg` |
| 视图-表格 | 表格网格 | `global_menu`（汉堡） | `view_table.svg` |
| 快速操作 | 蓝色文档系 | 纯 `action_add` 等 | `p01_quick_*.svg` + 36px 蓝底 |
| KPI 尺寸 | 36px 圆底 + 20px 图标 | 32px + 16px | `pm-project-card.css` |
| 空态插画 | 盒子+放大镜 | CSS 渐变占位 | `p01_empty_search.svg` |

## 剩余 C-fix（壳层 / 样本，非 P01 卡片）

1. 壳层：侧栏 IA 分组名、顶栏用户部门、flat 背景（`ops_shell.css`）
2. A01：导入或归档 1 个演示项目后复验灰化卡
3. 演示密度：设计 16 项 + 分页 2 页 — 需 seed 数据或接受真实 5 项
