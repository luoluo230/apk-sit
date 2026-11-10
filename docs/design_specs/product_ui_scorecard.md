# 管理端商业 UI 验收打分卡（八维）

> **真源**：配合 [workstation_ui_system.md](./workstation_ui_system.md) 与 [P3-02](../architecture/plans/P3-02_workstation_ui_commercial.md)。  
> **结案规则**：单页八维全部 `PASS` 才可标该页商业可用；任一为 `FAIL` 则整页 `FAIL`；未测为 `UNKNOWN`。

## 八维定义

| 维 | 代号 | 验收要点 |
|----|------|----------|
| 1 | **壳层** | `ops_shell` 内渲染；无独立 Tailwind/CDN 壳 |
| 2 | **Token** | 颜色/圆角/间距来自 `design-tokens.css`，无页内乱写色板 |
| 3 | **信息架构** | 标题区 + 筛选 + 主内容骨架符合规范 §3 |
| 4 | **组件** | `pm-btn` / `pm-table` / `pm-filter-bar` 等复用，无散装按钮 |
| 5 | **空错载** | 空态/错误/加载有中文说明 + 可点主操作 |
| 6 | **密度可读** | 表格/表单不挤、对比度足够、标签语义色一致 |
| 7 | **主路径可用** | 本页声明的主按钮/链接 E2E 可走通（非假按钮） |
| 8 | **文案** | 可见中文无乱码、无中英垃圾串 |

状态枚举：`PASS` | `FAIL` | `UNKNOWN`（未浏览器复验）

## 页面矩阵（2026-11-10 浏览器复验）

> 复验方式：已登录浏览器访问；CDP 检查无 `tailwind.css` / cdnjs；可见中文空态与主操作。

| 页面 | 路径 | 壳层 | Token | 信息架构 | 组件 | 空错载 | 密度 | 主路径 | 文案 | 整页 |
|------|------|------|-------|----------|------|--------|------|--------|------|------|
| 工作台 | `/admin` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 项目列表 | `/admin/projects` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 成员 | `/admin/users` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 站点外壳 | `/admin/site-config` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 项目总览 | `.../overview` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 环境运行 | `.../environments/{env}` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 发版中心 | `.../release-hub` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 服务器管理 | `.../server-management` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| Agent 控制 | `.../agents` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 休闲服务 | `.../casual-services` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| BaaS GM | `.../baas-gm` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 项目任务 | `.../tasks` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 审批中心 | `.../approval` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| 文档中心 | `/docs` | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |

> 说明：站点外壳表单页已进 `ops_shell`（2026-11-10）；可视化编辑器保留独立壳（`workstation_ui_system.md` 例外），不计入本矩阵 FAIL。

## 复验记录

| 日期 | 操作者 | 范围 | 证据 |
|------|--------|------|------|
| 2026-11-10 | — | 初版建档 | `docs/evidence/2026-11-10/OPEN-2026-11-10-29.json` |
| 2026-11-10 | agent | 浏览器登录复验工作室+项目主路径；无全局 Tailwind | `docs/evidence/2026-11-10/P3-02.json` |
