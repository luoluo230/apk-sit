# P3-02 管理端商业 UI 统一

## 目标

按 [workstation_ui_system.md](../../design_specs/workstation_ui_system.md) 把仍像 demo 的管理页收进同一套 `ops_shell` + `pm-*` 组件，可上线使用。  
不新开业务能力；接口与权限不变。

## 非目标

玩家站、论坛像素改版；iOS / 微信真发 / gameserver 进程阻塞项。

## Steps

### Step 1：规范与工作台
- 规范文档已作为真源。
- 工作台：待办分组 + 快捷入口 + 最近项目。

### Step 2：协作主路径
- 项目任务列表与创建表单（模态）。
- 文档中心迁入 ops_shell，去掉独立 Tailwind 壳与模块墙噪音。

### Step 3：工作室其余页
- 我的任务、审批、消息、成员、打包机列表、站点外壳。

### Step 4：收尾
- 任务统计、报表、审计、系统设置；更新 `workstation_ui_system.md` 状态表。

## 门禁

每 Step：`py_compile` 改过的 Python；改过的 JS `node --check`；浏览器验证该波主路径无 tailwind/cdnjs、空态有主操作、主按钮可用。
