# 管理台壳层

视觉真源是现有运维工作台，不是新的一套皮肤。

- 壳模板：`portals/common/core/templates/ops_shell.html`
- 色板：`portals/common/core/static/project_ui/design-tokens.css`
- 主色 `#1677FF`，弱底 `#E8F1FF`，页面底 `#F6F8FC`，正文 `#1F2A37`，弱字 `#6B7280`，分割线 `#E5EAF3`
- 状态色：成功 `#52C41A`，警告 `#FAAD14`，危险 `#FF4D4F`，信息 `#13C2C2`
- 圆角 4 / 8 / 12 / 16 / 20。阴影使用 token 里的 `--shadow-sm` 到 `--shadow-lg`
- 字体：Inter、PingFang SC、Microsoft YaHei、Noto Sans SC
- 左侧导航宽 232px，收起后 64px。顶栏含面包屑、项目切换、搜索、帮助、通知、用户
- 内容区白面板，页面内边距 24px

## 谁用这层壳

管理台页面都进 `ops_shell`。旧的深色顶栏只保留在 `_admin_layout` 的历史字符串里，运行时改为调用同一套壳。

BaaS / GM 的功能导航留在内容区（配置项、GM 业务域），不再套第二套应用侧栏。`BAAS_STANDALONE=1` 时只渲染内容区和同一套顶栏，色板仍是上面的 token。

玩家站模板不使用这层壳。

## 构建页

`/admin/build` 和项目内旧构建页进入项目工作区的构建与产物（`/admin/projects/<id>/build-history`）。没有项目上下文时回到项目列表。

## 空、加载、错误

- 加载：内容区写「正在加载…」，不要用空白面板冒充完成
- 空：说明没有数据，并给出本页主操作
- 错误：危险色边框，文案写明失败原因，保留重试或返回

## 验收

导航高亮、项目切换、以及一条真实操作（打开发版中心或 BaaS 功能开关）仍然请求原来的 API。
