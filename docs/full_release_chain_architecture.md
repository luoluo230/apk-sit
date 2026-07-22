# 全链路流程架构设计

更新时间：2026-06-11  
状态：唯一真源

## 1. 目标

目标只有一个：你把资源、配置、APK、发版信息、服务器都准备好后，可以按一条固定流程发布，不会中途因为参数漂移、状态不同步、拓扑不一致、接口兜底错误而被打断。

这份文档覆盖：

- Jenkins
- Web 版本管理
- GM 发布与回滚
- Ops / Topology / Agent
- 后端服务器运行态
- 客户端热更与启动

## 2. 全链路总览

链路分成八段：

1. 项目注册与真源
2. Jenkins / Unity / OSS 构建上传
3. Web 版本管理
4. GM 发布与回滚
5. Ops / 拓扑 / Agent / cluster
6. 后端服务器运行态
7. 客户端热更与启动
8. 端到端对账

闭环原则：

- Jenkins 负责产物
- Web 负责版本与发布状态
- Ops 负责运行拓扑与实例状态
- Client 只消费已发布 bundle 快照

## 3. 统一主键

内部统一主键只能用这套：

| 字段 | 含义 | 真源 |
|---|---|---|
| `project_id` | 平台项目标识 | project manifest / project registry |
| `env_key` | 环境键，固定 `development/testing/staging/production` | Env 归一规则 |
| `channel_id` | 渠道主键 | project manifest |
| `scope_id` | 发布作用域，格式 `{project_id}:{env_key}:{channel_id}:{platform}` | release scope |
| `version_name` | 客户端展示版本 | VersionRow / 构建参数 |
| `version_code` | 精确构建号 | VersionRow / 构建参数 |
| `platform` | `android` / `ios` | 构建参数 / 客户端 |
| `bundle_id` | 一次发布的原子快照 | release bundle |
| `active_bundle_id` | 当前 scope 生效快照 | VersionRow + ReleaseBundle |
| `topology_id` | 当前服务端拓扑快照 | Ops topology |
| `runtime_run_id` | 当前运行实例快照 | Ops runtime |
| `game_id` | 客户端项目凭证 | GM project credentials |
| `game_key` | 客户端项目凭证 | GM project credentials |

兼容别名只允许输入时归一，不允许内部继续扩散：

- `env` / `stage` -> `env_key`
- `channel` / `channel_key` -> `channel_id`

## 4. 核心数据模型

### 4.1 ProjectReleaseManifest

定义项目支持的：

- `project_id`
- `game_id`
- `game_key`
- 渠道列表
- 平台列表
- 默认路径模板

### 4.2 ReleaseScope

唯一定位一条发布线：

- `scope_id`
- `project_id`
- `env_key`
- `channel_id`

### 4.3 VersionRow

记录某个客户端版本和构建产物：

- `version_name`
- `version_code`
- `platform`
- `apk_url`
- `resource_url`
- `config_url`
- `publish_status`
- `active_bundle_id`

### 4.4 ReleaseBundle

一次正式 publish 的原子快照，锁定：

- client 三件套路径
- `scope_id`
- `bundle_id`
- `topology_id`
- `runtime_run_id`
- `network_profile`
- 审批、发布时间、发布人
- `supersedes_bundle_id`
- `rollback_of_bundle_id`

### 4.5 NetworkProfile

客户端联网真源：

- `gateway_ws`
- `login_http`
- `game_ws`
- `ops_http`
- `notice_url`

## 5. 四段主流程

### 5.1 Jenkins

输入最少字段：

- `project_id`
- `env_key`
- `channel_id`
- `platform`
- `version_name`
- `version_code`

产出要求：

- APK
- resource 包
- config 包
- catalog
- config manifest
- code manifest

Jenkins 只负责：

- 构建
- 上传 OSS
- 回写版本产物信息

Jenkins 不允许负责：

- 写 gateway 地址
- 写 topology
- 写 runtime 真源
- 直接决定 public 发布结果

### 5.2 Web / GM 发布

Web 负责：

- 版本登记
- scope 解析
- precheck
- 审批
- publish
- rollback
- public bootstrap

发布动作必须原子完成：

1. precheck 通过
2. 生成新 bundle
3. 旧 published bundle 标记 superseded
4. 当前版本行写入 `active_bundle_id`
5. 同 scope 同 platform 其他版本行状态同步降级

### 5.3 Ops / Topology / Agent

Ops 负责：

- 当前环境 active topology
- agent 绑定
- 远程启动
- runtime active 状态
- cluster 同步

发布前必须能回答：

- 当前 `project_id + env_key` 的 active `topology_id` 是谁
- 当前 topology 是否已经有 active runtime
- `network_profile` 是否从 active topology 正确构建

### 5.4 Client

启动顺序固定：

1. 请求 `runtime-bootstrap`
2. 获取 `bundle_id + network_profile + bootstrap paths`
3. 热更 catalog/config/code
4. 注入网络参数
5. 登录 gateway

非 Editor / 非开发模式下：

- 不允许本地 `ProtocolNetworkSettings` 静默覆盖 bootstrap
- 不允许从非 published 版本回退取地址

## 6. 必查接口

### 6.1 Jenkins / Build

- `POST /admin/build/trigger`
- `GET /api/build/<build_number>/status`
- `POST /api/build/<build_number>/finalize-apk`
- `POST /admin/build/commercial-release/trigger`
- `POST /admin/build/commercial-release/activate`

### 6.2 Release / GM

- `GET /api/runtime/version-resolve` — 兼容层；响应含 `deprecated` 与 `prefer_runtime_bootstrap`
- `GET /api/public/release-config` — scope / network / bootstrap_paths（与 runtime-bootstrap 字段对齐）
- `GET /api/public/runtime-bootstrap` — 客户端唯一真相入口（active bundle + rollout_percentage / rollout_bucket 灰度分桶）
- `POST /api/webhooks/approval/{provider}` — 外部审批回调（Feishu/DingTalk，签名校验，幂等 approval_id）
- `POST` generic webhook 事件：`release_awaiting_approval`、`bundle_published`、`approval_sla_timeout`
- 发布成功后可选 `network_profile.catalog_reload_url` POST 通知服务端 reload catalog
- `GET /api/release/scopes/<scope_id>?platform=android` — platform 必填或四段 scope_id
- `GET /api/release/bundles`
- `POST /api/gm-ops/release/versions` — **deprecated**，薄包装 → ReleaseOrder API
- `POST /api/gm-ops/release/precheck` — **deprecated**，薄包装 → `POST .../release-orders/<id>/precheck`
- `POST /api/gm-ops/release/publish` — **deprecated**，薄包装 → Journey / ReleaseOrder publish
- `POST /api/gm-ops/release/rollback` — **deprecated**，薄包装 → ReleaseOrder rollback

推荐路径：Channel Build/Release Journey → ReleaseOrder API（`/api/projects/<id>/delivery/...`）。

### 6.3 Ops / Runtime

- `GET /api/ops-platform/topologies`
- `GET /api/ops-platform/topology`
- `POST /api/ops-platform/topology/node/start-remote`
- `GET /api/ops-platform/runtime/active`
- `POST /api/ops-platform/cluster/sync`
- `GET /api/ops-platform/agents`
- `POST /api/ops-platform/agent/register`
- `POST /api/ops-platform/agent/heartbeat`

## 7. 发布门禁

### 7.1 构建前

- `project_id / env_key / channel_id / platform / version_name / version_code` 必须齐
- 版本号在同 scope + platform 下不能歧义

### 7.2 上传后

发布前必须做 OSS 可达性校验：

- `apk_url`
- `resource_url`
- `config_url`
- `catalog_url`
- `config_manifest_url`
- `code_manifest_url`

要求：

- 全量 HEAD 可达
- 任一失败则 precheck 失败

### 7.3 发布前

必须同时满足：

- scope 已存在
- active topology 已解析
- topology 与 runtime 对齐
- network profile 可构建
- 审批通过
- 产物可达

### 7.4 Public API

public API 只允许返回：

- `published`
- `precheck` 通过
- 与 active bundle 对齐的版本

禁止：

- 找不到 published 后回退 draft
- 用查询命中的旧 VersionRow 冒充 active bundle

## 8. 当前已修复项

本轮已经落地的关键修复：

### 8.1 precheck 前推到 OSS

`run_scope_precheck()` 已增加产物可达性检查，直接校验：

- APK
- resource
- config
- catalog
- config manifest
- code manifest

没有这些文件，不能发布。

### 8.2 publish / rollback 状态同步

发布或回滚后，Web 侧会同步同一 `scope_id + platform` 下的版本行：

- 当前激活版本：`publish_status=published`
- 其他版本：`publish_status=superseded`
- 激活版本写入正确 `active_bundle_id`

### 8.3 public payload 统一

`release-config` 与 `runtime-bootstrap` 现在都会对齐 active bundle，并统一返回：

- `scope_id`
- `bundle_id`
- `topology_id`
- `runtime_run_id`
- `topology_version_label`

### 8.4 rollback 审计链补全

回滚结果会保留：

- `rollback_of_bundle_id`
- 新的 `bundle_id`
- 被替换关系
- 当前重新激活版本

### 8.5 runtime 绑定补全

publish 时如果已经存在 active runtime，会自动把 `runtime_run_id` 带入 bundle。

## 9. 实际操作顺序

你真实发版时按这条顺序走：

1. 在 Jenkins 或 Unity 流水线完成资源、配置、APK 构建
2. 确认 OSS 上 APK、resource、config、catalog、manifest 都存在
3. 在 Web 录入或同步版本信息
4. 在 Ops 确认目标环境 topology 已部署，runtime 已激活
5. 在 Web 发起 precheck
6. precheck 通过后提交审批
7. 审批通过后 publish
8. 客户端启动走 `runtime-bootstrap`
9. 客户端热更完成后连接 bundle 对应 `gateway_ws`
10. 如需回滚，直接针对目标 scope 执行 rollback

## 10. 打通判定标准

算真正打通，必须同时满足：

- 同一 `scope_id` 任意时刻只有一个 published bundle
- `version-resolve`、`release-config`、`runtime-bootstrap` 返回同一个 active bundle
- `bundle_id`、`topology_id`、`runtime_run_id` 能互相对账
- topology 变更后不重新 publish 时，发布门禁能拦住
- rollback 后能恢复到上一条可用发布链
- 客户端启动日志可反查 `scope_id + bundle_id + gateway_ws`

## 11. 当前结论

当前这条链路已经从“有骨架”推进到了“development 环境可完整演练”的状态，但仍有两个边界要清楚：

- 现在的持久化底座还是 JSON，适合当前单团队发布，不适合多人高并发同时发正式版
- `runtime_run_id` 只有在真实 active runtime 已登记时才会自动进入 bundle；如果服务器还没起，这个字段不会凭空生成

## 12. 与代码对应关系

关键代码入口：

- `portals/common/core/routes/gm_ops.py`
- `portals/common/core/services/release/bundle_service.py`
- `portals/common/core/routes/release/scopes.py`
- `portals/common/core/scripts/simulate_e2e_publish.py`

这份文档以这些实现为准。  
Web 框架和模块组织说明，见 `docs/web_framework_design.md`。
