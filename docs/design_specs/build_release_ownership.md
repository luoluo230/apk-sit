# 构建—发版管线分层归属（Build & Release Ownership）

> 本文档定义 `apk-site` 中"构建参数 / 发布参数"的层级归属。每个字段都应该有且只有一个**唯一可写层**；其余层级**只读引用**。
>
> 配套设计文档：[`project_overview.md`](project_overview.md)、[`version_build_config.md`](version_build_config.md)。

## 1. 七层模型

```
Global Catalogs        渠道 / 平台 / Unity 版本目录       (平台管理员)
       ↓
Project Baseline       Git / Unity / 产物根 / 白名单       (项目管理员)
       ↓
Environment Policy     交付范围 / form_depth / 审批       (运维 / SRE)
       ↓
Channel Binding        渠道级 Job / 包名后缀 / 签名 ref   (项目工程师)
       ↓
Version Group     ★    pipeline_template / Jenkins / Bootstrap   (★ 构建管线唯一源 ★)
       ↓
VersionCode            只读快照 + 构建产物                (系统自动)
       ↓
Release Order          发布计划 + 状态机                  (运营 / 发布负责人)
```

## 2. 字段归属表

| 字段 | 归属层 | 修改入口 | 在 VC / 发布单 |
|---|---|---|---|
| `git_url`、`git_ssh_key_path`、`default_git_branch`、`git_branches[]` | Project | 项目 - 基线 Tab | 只读 |
| `unity_project_path`、`output_base_dir`、`app_name` | Project | 项目 - 基线 Tab | 只读 |
| `channels`、`disabled_channels`、`platforms`、`disabled_platforms` | Project | 项目 - 渠道 / 平台 Tab | 只读 |
| `release_environments[]` | Project | 项目 - 环境 Tab | 只读 |
| `channel_bindings[{channel_id, jenkins_job, package_suffix, signing_ref, notes}]` | Project（Channel Binding） | 项目 - 渠道 Tab - 渠道详情 | 只读 |
| `release_environments[].delivery_scope` | Environment | 项目 - 环境 Tab | 只读 |
| `release_environments[].release_policy`（`form_depth` / `require_approval` / 默认验证回滚 / `allow_gray_release`） | Environment | 项目 - 环境 Tab - 发布策略 | 只读，影响表单 |
| `release_environments[].network_profile`（gateway_ws、login_http 等） | Environment | 项目 - 环境 Tab | 只读，precheck 用 |
| **`version_groups[].pipeline_template`（4 步管线）** | **Version Group** | **版本组 - 配置管线** | **只读快照** |
| `version_groups[].jenkins_instance_id`、`jenkins_job_id`、`jenkins_job_overrides` | Version Group | 版本组 - 配置管线 | 只读 |
| `version_groups[].version_mode`（general / commercial） | Version Group | 版本组 - 配置管线 | 只读 |
| `version_groups[].resource_server_url`、`catalog_file_name`、`min_client_version`、`rollout_percentage`、`force_update`、`is_revoked`（Bootstrap） | Version Group | 版本组 - 配置管线 | 只读 |
| `versions[].version_name`、`version_code`、`channel`、`stage`、`platform` | VersionCode | 版本组 - 新建 VC | n/a |
| `versions[].pipeline`（仅历史快照） | VersionCode | 自动 / 迁移脚本写入 | 只读，新构建不读 |
| `release_orders.reason`、`payload.owner`、`release_window`、`release_strategy`、`gray_*`、`validation_*`、`rollback_*` | Release Order | 发布单编辑 | 发布单自身 |
| `release_orders.payload.jenkins_params`、`build_job_id`、`pipeline_source` | Release Order（系统写入） | 由 `request_build` 自动填充 | 只读 |

## 3. 解析顺序（resolve order）

### 3.1 构建管线 `resolve_effective_pipeline(project_id, vc)`

```
version_group.pipeline_template        ← 唯一源
        ↓ 若空（旧项目）
version.pipeline                       ← 兼容回退（不可写）
        ↓ 若仍空
_lazy_init_pipeline_template_from_siblings()  ← 从同组 VC 的旧 pipeline 反推
        ↓ 若仍空
{}（构建会被门禁拦截）
```

### 3.2 Bootstrap `resolve_effective_bootstrap_fields(project_id, vc)`

```
version_group.<key>          ← 唯一源
        ↓ 若空
version.<key>                ← 兼容回退（不可写）
```

### 3.3 Jenkins Job `resolve_jenkins_job(version, group_meta, channel_id, project_id)`

```
version_group.jenkins_job_overrides[channel]      ← 版本组级 override
        ↓
project.channel_bindings[channel].jenkins_job     ← 项目级渠道绑定
        ↓
version_group.jenkins_job_id                       ← 版本组默认 job
        ↓
version.jenkins_job_id                             ← 兼容回退（不可写）
```

### 3.4 Jenkins 实例 `resolve_effective_jenkins(project_id, vc)`

```
version_group.jenkins_instance_id     ← 唯一源
        ↓
version.jenkins_instance_id           ← 兼容回退（不可写）
```

## 4. 构建触发统一入口

所有 Jenkins 构建请求最终走：

```
release_order_service.request_build(project_id, order_id, actor)
        ↓
resolve_effective_pipeline + resolve_effective_jenkins
        ↓
plan_to_jenkins_params(...)  ← 单一 Jenkins 参数构造器
        ↓
jenkins_svc.trigger_build(...)
        ↓
status: building, payload.pipeline_source = "version_group"
```

### 兼容层路由

| 旧路由 | 新行为 |
|---|---|
| `POST /admin/build/trigger` (with `_version_id`) | 内部 `ensure_draft_release_order` → `request_build` |
| `POST /admin/build/commercial-release/trigger` (with `_version_id`) | 同上 |
| `POST /admin/build/trigger` (without `_version_id`，stage 构建) | 走旧的直触发流程（不影响） |
| `GET /admin/projects/{id}/versions/{vid}/workflow` | 仍可访问，但建议从「发布单」按钮进入 |

## 5. API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/projects/{pid}/versions/{vid}/effective-pipeline` | 返回 VC 当前生效的 pipeline + bootstrap + jenkins + readiness |
| GET | `/admin/projects/{pid}/channel-bindings` | 列出项目渠道绑定 |
| POST | `/admin/projects/{pid}/channel-bindings/update` | 更新单条渠道绑定 |
| POST/DELETE | `/admin/projects/{pid}/channel-bindings/delete` | 删除单条渠道绑定 |
| POST | `/admin/projects/{pid}/versions/update` | 普通 VC 更新；`edit_scope!=version_group` 时禁止写入管线/Bootstrap 字段 |

## 6. UI 约束

- 版本组管线页 (`/admin/projects/{pid}/versions/{vid}/build-config?from=version-group`) 是**唯一**可编辑构建管线的页面，页顶 banner 必须明示「这里是构建管线的唯一源」。
- 发布单页所有 Jenkins / 4 步管线字段强制 `readonly`，以"管线只读卡片"形式展示，并提供「前往版本组管线配置」CTA。
- 版本组列表行必须显示「管线就绪 / 管线未配置」徽章，未就绪时构建按钮禁用。
- VC 子行显示「继承自版本组」标签（未来增强）。

## 7. 迁移脚本

`portals/common/core/scripts/migrate_vc_pipeline_to_group.py`

- **默认 dry-run**：扫描所有项目，打印每个版本组的 VC pipeline 与 group template 差异。
- **`--apply`**：当版本组 `pipeline_template` 为空时，把同组最新 VC 的 pipeline 作为种子写入版本组，并传播到组内所有 VC。**不会**删除 VC 上的旧 pipeline 字段。
- 兼容字段：旧 VC `pipeline` 在 resolver 中作为最低优先级 fallback；不再可写。

## 8. 测试

- [`test_field_ownership.py`](../../portals/common/core/tests/test_field_ownership.py)：VC 层禁止写入受保护字段；从版本组读取生效。
- [`test_version_pipeline_config.py`](../../portals/common/core/tests/test_version_pipeline_config.py)：管线模板继承、深度合并、Jenkins 参数映射。
- [`test_release_policy_service.py`](../../portals/common/core/tests/test_release_policy_service.py)：readiness 评估、Job 解析顺序、`form_depth` 必填字段。
