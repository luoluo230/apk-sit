# 统一发版全链路审计与打通清单

更新时间：2026-06-11  
适用仓库：`E:/web/apk-site`  
基线规范：
- `docs/design_specs/unified_release_platform_architecture.md`
- `docs/release_platform_onboarding_evidence.md`
- `docs/ops_alignment/01_interface_matrix.md`
- `docs/ops_alignment/08_distributed_test_matrix.md`
- `portals/common/docs/gm_ops_release_gate.md`

## 1. 目标与判定方式

本文档用于审计以下全链路是否真实打通：

1. Web / 版本管理
2. Jenkins / Unity / OSS 构建上传
3. GM 发布与回滚
4. Ops 运维 / 拓扑 / Agent / `cluster.json`
5. 后端服务器运行态
6. 客户端热更 / 启动 / 登录

每段统一使用以下结论标签：

- `FULL_MATCH`：设计、接口、运行态、证据已闭环
- `PARTIAL_MATCH`：可用但字段、状态机、证据或运行态仍不完整
- `UI_ONLY`：仅页面或平台逻辑，未打到真实服务端执行
- `NOT_WIRED`：设计存在，但当前仓库内未接通

## 2. 当前全链路分段结论

| 段 | 范围 | 当前结论 | 当前依据 |
|---|---|---|---|
| A | 项目注册与真源 | `PARTIAL_MATCH` | `ProjectReleaseManifest`、`ReleaseScope`、`game_id/game_key` 在 GomeKu 上有证据，第二项目未完成 |
| B | Jenkins / Unity / OSS | `PARTIAL_MATCH` | 架构文档、commercial pipeline 入口、OSS 路径规范已定义，但缺少真 Jenkins Step1-4 全链路证据 |
| C | Web 版本管理 | `PARTIAL_MATCH` | `scope_id/env_key/active_bundle_id` 已落地并有开发环境证据，正式多环境/多渠道未全验 |
| D | GM 发布与回滚 | `PARTIAL_MATCH` | publish/precheck/bundle 已落地，rollback 有实现但缺少真实运行证据矩阵 |
| E | Ops / 拓扑 / Agent / cluster | `PARTIAL_MATCH` | `docs/ops_alignment/01_interface_matrix.md` 证明拓扑/Agent 主链路较强，但 release-side 对账仍需按 scope/bundle 逐项核 |
| F | 后端服务器运行态 | `PARTIAL_MATCH` | 运行编排层较强，业务进程层是否真实消费对应快照仍需专项验证 |
| G | 客户端热更与启动 | `PARTIAL_MATCH` | `runtime-bootstrap`、gateway `:15050`、PlayMode 登录已有证据；完整热更与多平台未全验 |
| H | 端到端闭环 | `PARTIAL_MATCH` | `gomeku:development:1001` 闭环有证据，`staging/production`、多渠道、多平台没有完整证据 |

## 3. 分段审计模板

每一段统一按下面 6 项填写，禁止只写“已完成/未完成”：

### 3.1 真实入口
- 路由
- 页面
- 脚本
- 数据文件
- 配置文件
- 外部仓库/依赖位置

### 3.2 输入参数
- 谁传递
- 字段名
- 允许别名
- 内部最终归一字段

### 3.3 输出结果
- 返回字段
- 状态字段
- 快照字段
- 审计/trace 字段

### 3.4 真源定义
- 本段唯一真源
- 兼容输入
- 禁止继续作为真源的旧字段

### 3.5 当前状态
- `FULL_MATCH / PARTIAL_MATCH / UI_ONLY / NOT_WIRED`

### 3.6 风险与断点
- 参数漂移
- 地址漂移
- 状态不同步
- 未真实消费
- 只有 UI，没有真实执行

## 4. 参数一致性基线表

| 分类 | 统一字段 | 当前别名/兼容输入 | 说明 |
|---|---|---|---|
| 项目标识 | `project_id` | 无 | 平台项目唯一标识 |
| 项目凭据 | `game_id`, `game_key` | 无 | 客户端 `runtime-bootstrap` 认证入口 |
| 作用域 | `env_key` | `env`, `stage`, `environment`, `profile` | 统一归一到 `development/testing/staging/production` |
| 作用域 | `channel_id` | `channel`, `channel_key` | 内部以 `channel_id` 为准 |
| 作用域 | `scope_id` | 无 | `{project_slug}:{env_key}:{channel_id}` |
| 客户端版本 | `version_name` | `client_version` | 客户端请求必须显式带 |
| 客户端版本 | `version_code` | 无 | 同 scope 精确构建号 |
| 平台 | `platform` | 无 | `android/ios` |
| 发布快照 | `bundle_id` | 无 | 一次发布的原子快照 |
| 发布快照 | `active_bundle_id` | 无 | 当前生效 bundle |
| 发布状态 | `publish_status` | `version_status` | 建议发布链只以 `publish_status` 为准 |
| 服务端快照 | `topology_id` | 无 | 拓扑快照标识 |
| 服务端快照 | `runtime_run_id` | 无 | 当前运行实例标识 |
| 服务端快照 | `topology_version_label` | 无 | cluster/runtime 快照标签 |
| 网络参数 | `gateway_ws`, `login_http`, `game_ws`, `ops_http`, `notice_url` | legacy profile 字段 | 最终由 `network_profile` 暴露 |
| OSS 路径 | `apk_url`, `resource_url`, `config_url` | 无 | 产物绝对地址 |
| OSS 路径 | `resource_relative_path`, `config_relative_path`, `code_relative_path`, `catalog_file_name` | 无 | 运行时相对路径 |

## 5. 接口 / 地址 / 文件核查清单

### 5.1 Web 公共接口
- `GET /runtime/version-resolve`
- `GET /api/public/release-config`
- `GET /api/public/runtime-bootstrap`

### 5.2 GM / Release 接口
- `POST /api/gm-ops/release/precheck`
- `POST /api/gm-ops/release/publish`
- `POST /api/gm-ops/release/rollback`
- `GET /api/release/scopes`
- `GET /api/release/scopes/{scope_id}`
- `GET /api/release/bundles`
- `GET /api/release/bundles/{bundle_id}`

### 5.3 Ops / Agent / Topology 接口
- `GET /api/ops-platform/topology`
- `POST /api/ops-platform/topology/save`
- `POST /api/ops-platform/topology/node/bind-agent`
- `POST /api/ops-platform/topology/auto-bind-agents`
- `POST /api/ops-platform/topology/node/start-remote`
- `GET /api/ops-platform/runtime/active`
- `POST /api/ops-platform/agent/register`
- `POST /api/ops-platform/agent/heartbeat`
- `POST /api/ops-platform/agent/pull`
- `POST /api/ops-platform/agent/report`

### 5.4 数据 / 配置 / 运行态文件
- `data/project_release_manifests.json`
- `data/release_scopes.json`
- `data/release_bundles.json`
- `project_versions_db`
- `E:/maclient/game-server/config/cluster.json`
- `HotUpdateConfig.asset`
- `ProtocolNetworkSettings.asset`

### 5.5 关键外部路径与命令
- OSS 模板：`{oss_project_root}/{Environment}/{Channel}/{Platform}/...`
- `py portals/common/core/scripts/release_platform_ci_gate.py --scope-id gomeku:development:1001`
- `py portals/common/core/scripts/verify_e2e_release.py`
- `py portals/common/core/scripts/commercial_startup_sequence_gate.py`
- `pytest tests/ops_distributed -m fast -q`
- `python tools/run_distributed_acceptance.py --game-server-repo E:/maclient/game-server --base http://127.0.0.1:5003`
- `powershell -File E:/maclient/game-server/tools/SmokeTest/DistributedAcceptance.ps1`
- `powershell -File E:/maclient/game-server/tools/Check-Cluster-Health.ps1`

## 6. 按段落的必查内容

### A. 项目注册与真源
- 检查 `ProjectReleaseManifest`、`projects_db`、`release_scopes.json` 中的 `project_id/project_slug/game_id/game_key/channels` 是否一致
- 检查 `scope_id` 是否已按 `env_key x channel_id` 自动生成
- 结论输出：
  - GomeKu 是否打通
  - 第二项目是否仅设计、未验证

### B. Jenkins / Unity / OSS 构建上传
- 检查 commercial release 入口、Jenkins 产物字段、OSS 目录模板
- 检查 `project_id/env_key/channel_id/platform/version_name/version_code` 是否能从构建层传到 Web
- 核查是否存在真实 Step1-4 证据，而不是仅设计描述

### C. Web 版本管理
- 检查 VersionRow 是否都具备 `scope_id/env_key/version_name/version_code/platform`
- 检查 `active_bundle_id` 与 `publish_status` 是否闭环
- 检查 `version-resolve/release-config/runtime-bootstrap` 的参数归一是否一致

### D. GM 发布与回滚
- 检查 precheck、publish、rollback、approval 的请求体和返回体
- 检查返回里是否统一暴露 `scope_id/bundle_id/active_bundle_id/topology_id/runtime_run_id`
- 检查是否具备 trace/audit 和回滚证据

### E. Ops / 拓扑 / Agent / cluster
- 检查 topology 保存、Agent 绑定、start-remote、runtime active 恢复、cluster sync
- 检查 `topology_id/runtime_run_id` 是否能回写到发布链路
- 检查 `network_profile` 是否真实来自拓扑而不是页面假值

### F. 后端服务器运行态
- 分开判断两层：
  - `运行编排层`：拓扑、Agent、cluster、runtime 是否闭环
  - `业务进程层`：game-server 内部是否真实消费当前快照
- 检查 game-server 侧 health/smoke/distributed acceptance 是否带 topology 上下文

### G. 客户端热更与启动
- 检查 `HotUpdateConfig.ProjectId/Channel/Profile`
- 检查 `runtime-bootstrap -> paths -> network_profile -> login` 顺序
- 检查是否仍存在本地 `ProtocolNetworkSettings` 抢真源

### H. 端到端闭环
- 检查 `active_bundle_id`、`gateway_ws`、`scope_id`、`topology_id` 是否可互相对账
- 检查至少一条 `development` 真实闭环
- 标记 `staging/production`、多渠道、多平台是否已有证据

## 7. 打通判定矩阵

| 能力点 | 设计期望 | 当前实现入口 | 当前证据 | 当前结论 | 缺失验证 | 下一步检查 |
|---|---|---|---|---|---|---|
| Manifest -> ReleaseScope | 项目注册后自动生成全 scope | `manifest_service.py`, `data/release_scopes.json` | `release_platform_onboarding_evidence.md` 步 1/2 | `PARTIAL_MATCH` | 第二项目证据 | 比对 manifest/scopes 数据 |
| Jenkins 产物参数 -> VersionRow | 构建参数只写入版本层 | `commercial_release_plan.py`, GM 版本库 | 设计文档 §7 | `PARTIAL_MATCH` | 真 Jenkins 证据 | 抽样 Step1-4 与版本行 |
| VersionRow -> Bundle | publish 锁定客户端+服务端快照 | `bundle_service.py`, `/api/gm-ops/release/publish` | development `1001` publish 证据 | `PARTIAL_MATCH` | rollback 真实证据 | 真实 publish/rollback 审计 |
| Bundle -> runtime-bootstrap | 客户端启动只认 published bundle | `/api/public/runtime-bootstrap` | onboarding 步 7a | `PARTIAL_MATCH` | staging/production、多渠道 | curl 实测多 scope |
| topology -> network_profile | 客户端地址来自当前拓扑 | `scope_resolver.py`, ops topology/runtime | gateway `:15050` 证据 | `PARTIAL_MATCH` | 渠道 override 多样本 | scope/profile 对账 |
| topology -> cluster.json -> runtime | 拓扑同步后形成真实运行态 | ops topology/runtime/agent API | `01_interface_matrix.md` B 段 | `PARTIAL_MATCH` | release-side 绑定证据 | runtime active + cluster diff |
| Agent start-remote -> runtime_run | 远端启动产生可追踪运行实例 | `POST /api/ops-platform/topology/node/start-remote` | `01_interface_matrix.md` B 段 | `FULL_MATCH`（编排层） | 业务进程消费证据 | live distributed acceptance |
| runtime-bootstrap -> HotUpdate -> login | 客户端先 bootstrap 再热更再登录 | `commercial_startup_sequence_gate.py`, Unity acceptance | onboarding 步 7b | `PARTIAL_MATCH` | 完整 basic 场景、多平台 | Unity basic + live login |
| rollback -> active_bundle_id 反切 | 回滚后客户端和服务端都能对账 | `/api/gm-ops/release/rollback`, bundles | 有实现，无完整证据 | `PARTIAL_MATCH` | 真实回滚链证据 | 回滚后 bootstrap 对账 |

## 8. 执行顺序建议

1. 先跑文档与数据层
   - manifest / scope / bundle / version row / topology 注册信息
2. 再跑接口与参数层
   - `version-resolve` / `release-config` / `runtime-bootstrap`
   - release publish / rollback / precheck
3. 再跑运行态层
   - topology active / runtime / cluster / agent / gateway
4. 最后跑端到端层
   - development `1001`
   - staging / production
   - 多渠道
   - 多平台

## 9. 本轮输出要求

执行本清单时，最终必须给出：

- 已有证据
  直接引用仓库现有 evidence / interface matrix / test matrix / gate script
- 缺失证据
  明确指出哪段只有设计，没有真实运行证明
- 打通结论
  每段给出 `已打通 / 部分打通 / 未打通 / 仅 UI`
- 风险清单
  只列真实断点，不写泛泛描述

