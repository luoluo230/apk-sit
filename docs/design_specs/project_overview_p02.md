# P02 项目总览 — A0 建档与验收

## 真源

| 项 | 值 |
|---|---|
| 设计图 | `docs/design_assets/project_management/P02_project_overview_10_54_38.png` |
| 基准视口 | 1680 × 960 |
| 运行 URL | `http://127.0.0.1:5003/admin/projects/{project_id}/overview` |
| 模板 | `portals/common/core/templates/project_overview.html` |
| 样式 | `project_overview.css` + `project_ui/pm-kpi.css` |
| 脚本 | `project_overview.js`（主仪表盘）+ `project_delivery.js`（仅 `?tab=` 配置态） |
| Cache 版本 | `20260630-p02-icons` |
| 验收截图 | `docs/evidence/2026-06-30/p02-project-overview-1680.png` |

## 主态清单

| 主态 | 进入方式 |
|---|---|
| 默认总览 | `/admin/projects/{id}/overview` |
| 环境配置 | `?tab=environments` |
| 渠道配置 | `?tab=channels` |
| 平台配置 | `?tab=platforms` |

## 图标映射（2026-06-30 p02-icons）

| 区域 | 设计语义 | 资源文件 | 来源/备注 |
|---|---|---|---|
| KPI 当前版本 | 蓝色立方体/版本包 | `kpi_version.svg` | Lucide box（MIT） |
| KPI 服务健康度 | 绿色心跳/波形 | `kpi_health.svg` | Lucide activity（MIT） |
| KPI 今日构建 | 紫色火箭 | `kpi_build.svg` | Lucide rocket（MIT） |
| KPI 待处理变更 | 橙色文档 | `kpi_change.svg` | 设计包原有 |
| KPI 项目成员 | 蓝色人群 | `kpi_member.svg` | 设计包原有 |
| 环境·开发 | 蓝色服务器 | `env_development.svg` | Lucide server（MIT） |
| 环境·测试 | 青色烧瓶 | `env_testing.svg` | Lucide flask（MIT） |
| 环境·预发 | 橙色层叠 | `env_staging.svg` | Lucide layers（MIT） |
| 环境·生产 | 红色盾牌 | `env_production.svg` | Lucide shield（MIT） |
| 视图·卡片 | 四宫格 | `view_grid.svg` | Lucide layout-grid（MIT） |
| 视图·列表 | 表格 | `view_table.svg` | 设计包原有 |

## A0 行级清单（38.png → 实现对照）

图标按上表映射验收；布局/间距/文案仍零容差。

### 页面标题与筛选条

| ID | 设计元素 | 设计规格 | 实现位置 | 结果 |
|---|---|---|---|---|
| H01 | 收藏星标 | 标题左侧星形按钮 | `.pm-page-star` | PASS |
| H02 | 标题 | 「项目总览」24px/600 | `.p02-head h1` | PASS |
| H03 | 筛选·项目 | 灰标签 + 白底 pill 项目名 | `.p02-filter-pill--project` | PASS |
| H04 | 筛选·环境 | 绿色 pill「全部环境」 | `.p02-filter-pill-select--env` | PASS |
| H05 | 筛选·渠道 | 蓝色 pill「全部渠道」 | `.p02-filter-pill-select--channel` | PASS |
| H06 | 筛选·平台 | 紫色 pill「多平台」 | `.p02-filter-pill-select--platform` | PASS |
| H07 | 数据更新时间 | 筛选条最右 + 刷新图标 | `.p02-filter-meta` | PASS |
| H08 | 无配置 Tab 条 | 默认态不出现运行概览/环境管理等 Tab | 模板移除 + `__P02_OVERVIEW__` | PASS |

### KPI 五卡

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| K01 | 布局 | 5 等宽横排，gap 16px | PASS |
| K02 | 当前版本 | 蓝圆底图标 + 版本号 +「版本详情 >」 | PASS |
| K03 | 服务健康度 | 绿圆底 + 百分比 + 趋势 +「健康概览 >」 | PASS |
| K04 | 今日构建次数 | 紫圆底 + 次数 + 趋势 +「构建与产物 >」 | PASS |
| K05 | 待处理变更 | 橙圆底 + 数字 +「变更治理 >」 | PASS |
| K06 | 项目成员 | 青圆底 + 人数 +「成员管理 >」 | PASS |

### 环境运行概览

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| E01 | 标题区 | 「环境运行概览」+ 帮助图标 | PASS |
| E02 | 右侧控件 | 环境下拉 + 卡片/列表视图切换（无「管理环境」主按钮） | PASS |
| E03 | 卡片数量 | 仅 dev/test/staging/prod 四卡，单行四列 | PASS |
| E04 | 卡头 | 图标 + 环境名 + 状态 badge | PASS |
| E05 | 三列字段 | 环境 / 渠道 / 平台 | PASS |
| E06 | 四指标 | 服务健康度 / 在线实例 / Agent 状态 / 更新时间 | PASS |
| E07 | 页脚链接 | 居中「环境详情 >」 | PASS |

### 最近动态

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| A01 | 标题 + 查看全部 | 右链「查看全部 >」 | PASS |
| A02 | 8 Tab | 全部/发布/构建/变更/告警/审批/任务/文档 | PASS |
| A03 | 列表行 | 色点 + 类型 pill + 描述 + 用户 + 时间 | PASS |

### 右栏

| ID | 设计元素 | 设计规格 | 结果 |
|---|---|---|---|
| R01 | 项目成员 | 头像 + 姓名 + 彩色角色 tag +「+ 邀请成员」 | PASS |
| R02 | 帮助与支持 | 4 链：使用文档/常见问题/提交工单/联系我们 | PASS |
| R03 | 快捷入口 | 2×2：发布单/构建与产物/拓扑资产/项目任务 | PASS |
| R04 | 右栏宽度 | 280px sticky | PASS |

### 壳层（共享 ops_shell，非本页独占）

| ID | 设计元素 | 结果 | 备注 |
|---|---|---|---|
| S01 | 四级面包屑 | PARTIAL | 壳层 breadcrumb 仍为简化路径 |
| S02 | 顶栏搜索 placeholder 全文 | PARTIAL | ops_shell 共用顶栏 |
| S03 | 用户部门副标题 | PARTIAL | 设计稿「研发中心」未接 HR 数据 |

## 交互抽检

| 动作 | 预期 | 结果 |
|---|---|---|
| 刷新按钮 | 更新时间刷新 + KPI/环境/动态重载 | PASS |
| 环境/渠道/平台筛选 | URL 参数更新 + 卡片重算 | PASS |
| 动态 Tab 切换 | 列表按类型过滤 | PASS |
| 环境视图切换 | 卡片/列表布局切换 | PASS |
| `?tab=environments` | 隐藏主布局，显示环境配置 + 返回链接 | PASS |

## 验收结论

- **P02 页面内容区（模板+CSS+JS）**：ALL PASS（图标 N/A）
- **共享壳层 S01–S03**：PARTIAL，不阻塞 P02 内容区交付；后续 ops_shell 迭代补齐
- **证据**：Playwright 1680×960 登录态截图已归档
