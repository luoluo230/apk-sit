# P3-01：工作站收敛（上线前最后一轮）

| 项 | 值 |
|----|-----|
| 优先级 | 上线前 |
| 预估 | 一轮，按 Step 1→5 顺序做完再部署 |
| 依赖 | 现有 ops shell、`shell_nav.py`、发版五扇门 |
| 依据 | 工作站评审（2026-10-29） |
| 状态 | 未开始 |

人用的管理端已经有一套侧栏。这一轮把环境、发版步骤和还在用旧皮肤的工作室页收成同一套工作站，然后按文末门禁部署。不新做功能。

---

## 1. 目标

进一个项目之后，顶栏选中的环境就是下一页的环境。发版四页能看出自己在哪一步。工作台、消息、成员、打包机、站点外壳和项目任务不再套 Tailwind。侧栏把拓扑游戏服和休闲服务分开说。

---

## 2. 范围

**In**

- 环境只有一个缺省值：`development`
- 项目内每个侧栏链接带上当前 `env_key`
- 发版中心、版本与管线、构建与产物、发版执行、发布历史共用一条步骤
- 侧栏分组改名，服务器管理不再重复放休闲服务页签
- 下载中心、测试设备进入侧栏
- 面包屑可点击，并与侧栏当前项一致
- 工作室六页和项目任务页改用 `design-tokens`，工作台改成待办
- 本轮改完后的部署检查

**Out**

- 不重做 P0–P2 已落地的发版状态机、服务端发布单、Ops 拆分
- 不把侧栏「发版」拆回五个入口。步骤条在页面里，侧栏仍是一个「发版」
- 不改玩家站、论坛前台
- 不重做 Jenkins 任务配置、构建参数、流水线脚本
- 不标记 iOS、微信小游戏真发、游戏服进程已部署。这三项仍是环境阻塞
- 不清理 `request_events`，不删 GomeKu / RecycleTycoon

---

## 3. 前置条件

- 管理端壳子是 `templates/ops_shell.html`，导航数据只在 `services/ops/shell_nav.py`
- 版本页没有 `env_key` 时已经 302 到 `development`（P1-06）。本轮缺省值跟它对齐，不改回 production
- 生产启动仍走 `require_production_secrets()` 和 `require_production_database()`，见 `docs/runbooks/deployment_topology.md`

已有测试 `test_shell_nav.py` 断言休闲服务链接不以 `env_key` 结尾，发版分组只有一项。Step 1 要改断言，不能绕开测试。

---

## 4. 分步实施

### Step 1：环境上下文只保留一处

缺省和环境的传递收口，页面业务不变。

改这些文件：

- `services/ops/topology/registry_crud_1.py`：`_resolve_ops_env_key` 在 query 和 session 都空时返回 `development`，不再返回 `production`
- `services/ops/shell_nav.py`：项目内每一项 href 都带 `env_key`。包括服务器管理、代理、动作、诊断、功能配置、GM、任务、文档、设置、审计、变更治理。游戏圈和审批继续用 `project_id`，并加上 `env_key`
- `templates/ops_shell.html`：`data-env-key` 和环境下拉的空值兜底改成 `development`
- `static/ops_shell.js`：空值兜底改成 `development`。切换环境仍只改当前 URL 的 query
- `routes/delivery/pages.py`：任务页不要再写死 `production`
- `templates/project_release_hub.html`：`env_key or 'development'` 保留，并与壳子一致

规则：

1. URL 里的 `env_key` 优先
2. 没有则用 session `ops_last_env`
3. 再没有则 `development`
4. 侧栏生成链接时使用已经解析好的这个值

**验收**

- [ ] 无 query、无 session 时，壳子环境是开发环境
- [ ] 当前是 `staging` 时，点服务器管理、GM、任务，地址仍带 `env_key=staging`
- [ ] 发版分组仍然只有一个「发版」
- [ ] `test_shell_nav.py` 更新后通过

### Step 2：发版四页共用步骤条

把发版中心已有的四步做成一块，五个页面都引用。不改发布单状态机。

- 新建 `templates/_release_steps.html`，四步：版本与管线、构建与产物、去发版、发布历史
- 当前步由 `active_page` 决定：`versions`、`builds`、`release-console`、`release-orders`，发版中心不高亮其中一步，只作为起点
- `project_release_hub.html` 去掉页内手写的四链接，改引用这块
- `project_versions_workspace.html`、`project_build_history.html`、`project_release_console.html`、`release_orders.html` 在页头引用同一块
- 样式放在现有发版 CSS，不新做皮肤。链接全部带当前 `env_key`

**验收**

- [ ] 五个页面都能看到同一条步骤，文案一致
- [ ] 在版本页，当前步是「版本与管线」；在发版执行页，当前步是「去发版」
- [ ] 点步骤不会丢掉 `env_key`
- [ ] 侧栏仍只有一个「发版」，五个页面都高亮它

### Step 3：导航说清两套服务器，补上藏着的页面

- `shell_nav.py` 分组改名：`运行` → `游戏服`，`运营` → `休闲服务`。项的 id 不变，避免页面 active 判断失效
- 设置组增加「测试设备」，指向 `/admin/projects/{id}/test-devices`
- 发版步骤条增加「下载中心」，不放进侧栏，避免发版入口再次变多
- `routes/server_management/pages.py`：项目内服务器管理只呈现拓扑游戏服。休闲服务仍从「功能配置 / GM」进入。全局 `/admin/server-management` 同样不再用页签切换两套产品

**验收**

- [ ] 侧栏能看见「游戏服」「休闲服务」「测试设备」
- [ ] 项目内服务器管理没有休闲服务页签
- [ ] 功能配置、GM 仍可打开
- [ ] 下载中心从发版步骤进入，并带当前环境

### Step 4：面包屑跟侧栏走

- 在 `shell_nav.py` 增加一个函数：根据 `active_page` 返回「分组名、项名、项链接」
- `ops_shell.html` 用它渲染：工作台（可点）/ 项目名（可点，进项目总览）/ 分组 / 当前页
- 没选项目时只显示「工作台 / 当前页」
- 各页传入的 `breadcrumb_module` 只在这个函数找不到项时作兜底

**验收**

- [ ] 在发版中心，面包屑最后一项是「发版」，点项目名回到该项目总览
- [ ] 在服务器管理，分组显示「游戏服」
- [ ] 面包屑不出现固定的「项目管理 / 项目工作区」

### Step 5：工作室页和任务页离开 Tailwind

只换这些页的呈现，不改接口和权限。

| 页面 | 路由 | 现在 | 改成 |
|------|------|------|------|
| 工作台 | `/admin` | 模块磁贴，Tailwind + Font Awesome | 待办：待审批、未读通知、逾期任务、缺包版本。数据仍用 `views/dashboard.py` 已有聚合 |
| 消息 | `/admin/notifications` | Tailwind | `design-tokens` 列表 |
| 成员 | `/admin/users` | Tailwind | 同一套表格和按钮 |
| 打包机 | `/admin/jenkins` | Tailwind | 列表页换皮。实例编辑和日志页保持能用，不重做 Jenkins |
| 站点外壳 | `/admin/site-config` | Tailwind 大表单 | 同一套表单控件 |
| 项目任务 | `/admin/projects/{id}/tasks` | 额外挂 Tailwind | 去掉这页的 Tailwind |

做法：

- `_admin_layout` 不再插入 `tailwind.css` 和 Font Awesome CDN
- 这些页的按钮、表格、空状态使用 `static/project_ui/design-tokens.css` 里已有的类
- 工作台每条待办能点进现有审批、通知、任务或版本页
- 没有待办时显示「当前没有要处理的事项」，不留空卡片

**验收**

- [ ] 上述六页的 HTML 不再引用 `tailwind.css` 和 `cdnjs.cloudflare.com`
- [ ] 工作台能看到待审批和未读，点击进入原来的页面
- [ ] 成员新增、打包机打开、站点保存仍走原来的接口
- [ ] 中文无乱码

---

## 5. 测试与门禁

每个 Step 结束都跑：

- `py -3 -m py_compile` 本 Step 改过的 Python
- `node --check` 本 Step 改过的 JS
- `py -3 -m pytest portals/common/core/tests/test_shell_nav.py portals/common/core/tests/test_delivery_scope.py`

Step 2 额外跑：

- `py -3 -m pytest portals/common/core/tests/test_release_hub.py portals/common/core/tests/e2e/test_release_hub_e2e.py`

Step 5 额外用浏览器看工作台、消息、成员、打包机、发版中心、服务器管理。确认环境切换后地址里的 `env_key` 不丢。

---

## 6. 回滚

每个 Step 单独可回退。Step 1 若线上环境被带偏，把 `_resolve_ops_env_key` 的最后返回值改回 `production`，并还原 `shell_nav.py`。Step 5 若页面不可用，恢复 `_admin_layout` 的 Tailwind 引用。不要用回滚去改发布单数据。

---

## 7. 部署门禁

五步验收都勾完之后才部署。部署本身不做新功能。

**要满足**

- [ ] `APP_ENV=production` 时，缺密钥或 `DATABASE_URL` 不是 PostgreSQL，进程拒绝启动
- [ ] 生产只跑一个已写明的模式：PostgreSQL，worker 数写进当次发布说明
- [ ] 本轮 pytest 通过
- [ ] 冒烟：登录 → 打开五子棋 → 环境切到 testing → 发版中心、版本页、服务器管理、功能配置的地址都带 `env_key=testing`
- [ ] 库里项目只有 GomeKu、RecycleTycoon
- [ ] 备份按 `docs/runbooks/production_backup_restore.md` 做完

**明确不在这次上线里**

| 项 | 状态 | 上线时怎么说 |
|----|------|----------------|
| iOS / TestFlight | 阻塞 | 界面不显示为已可发布 |
| 微信小游戏真发 | 阻塞 | 本机没有可用 Jenkins 与 WxMinigame Job |
| 游戏服进程启动 | 阻塞 | `IDeadLetterService` 类型加载失败，不标已部署 |
| 访问日志 `request_events` | 保留 | 这是访问记录，不是测试夹具 |

---

## 8. 完成定义

- [ ] Step 1–5 验收全勾
- [ ] §7 部署门禁全勾
- [ ] 阻塞三项仍标阻塞，没有被写成完成
