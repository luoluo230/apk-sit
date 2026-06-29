# VersionCode / 版本组管线模板配置

> 自 2026-06 分层重构起，**版本组 (`version_group`) 是构建管线的唯一可写源**；VersionCode 与发布单完全只读引用。字段归属表与解析顺序见 [`build_release_ownership.md`](build_release_ownership.md)。

主入口：`/admin/projects/{project_id}/versions` → 版本组行「配置管线」

备用入口：发布单 STEP02 →「前往版本组管线配置」（`from=release-order`，返回发布单）

## 参数层级与继承

| 层级 | 存储 | 典型内容 | 新建 VC 时 |
|------|------|----------|------------|
| 项目 | `project.build_config` | Unity 路径、APP_NAME、OUTPUT_BASE_DIR、Git | 自动填充 pipeline 空字段 |
| 环境 | `delivery_scope` + env | 可用渠道/平台 | 环境治理，不在本页编辑 |
| 渠道绑定（项目 × 渠道） | `project.channel_bindings[]` | `{channel_id, jenkins_job, package_suffix, signing_ref}` | Job 解析顺序中第二高优先级 |
| **版本组 ★** | `project.version_groups[].pipeline_template` + `jenkins_*` + bootstrap | 四步开关、压缩/热更策略、bootstrap 模板、Jenkins 实例/Job | **唯一可写**：保存后传播到组内所有 VC |
| VersionCode | `version.pipeline`（只读快照）、`version_name`、`version_code`、路径字段 | 继承模板 + `_derive_runtime_paths` | 仅填 VC 编号 / channel；管线/Bootstrap 写入会被服务端拦截（400） |
| 发布单 | `release_order.payload` | 负责人、灰度、验证/回滚；`pipeline_source=version_group` | **不编辑管线**（STEP02 只读管线卡片） |

继承链（保存时，`edit_scope=version_group`）：

```
project.build_config → apk_build 空字段默认值
保存到 version_groups[].pipeline_template + bootstrap + jenkins_* + jenkins_job_overrides
→ _propagate_pipeline_to_group_scope: 同 version_name × env × platform 全部 VC 写入 pipeline 快照
→ _derive_runtime_paths: 按各 VC 编号刷新 resource_path / config_path / apk_path
→ resolve_jenkins_job 重新解析每个 VC 的 jenkins_job_id（版本组 override > 项目渠道绑定 > 版本组默认）
```

VC update 写抦截：

```python
update_version(payload):
  if edit_scope != "version_group" and any({pipeline, jenkins_*, resource_server_url, catalog_file_name,
                                              min_client_version, rollout_percentage, force_update, is_revoked} in payload):
      return 400 {"error": "构建管线与 Bootstrap 字段只能在版本组层级编辑", "blocked_fields": [...]}
```

## 路由

| URL | 说明 |
|-----|------|
| `/admin/projects/{id}/versions/{vc_id}/build-config?from=version-group` | 主入口（anchor VC + 版本组模板编辑） |
| `/admin/projects/{id}/version-groups/build-config?from=version-group` | 无 VC 时仅编辑模板（保存走 version-groups/update） |
| `/admin/projects/{id}/versions/{vc_id}/build-config?from=release-order` | 发布单跳转，返回发布单 |

保存：`edit_scope: "version_group"`（默认）→ `versions/update` 或 `version-groups/update`。

## UI 壳层（对齐发布单 workflow）

视觉与结构母版：[`release_order_form.html`](portals/common/core/templates/release_order_form.html)

| 区域 | 类名 / 组件 |
|------|-------------|
| 页面根 | `delivery-app build-config-app` |
| 页头 | `workflow-heading` + `ui-primary` |
| 左导航 | `workflow-steps`（6 步，对应 `?section=`） |
| 主内容 | `workflow-section` + `section-title` + `form-grid` |
| 右侧栏 | `workflow-rail` + `ui-panel` |
| 底栏 | `workflow-footer` |

样式：`project_delivery.css` + `project_version_build_config.css`（`bc8`）。

## 客户端三域 ↔ Jenkins Step ↔ bootstrap

| 域 | 客户端加载 | Jenkins 步骤 | `RELEASE_TARGETS` | bootstrap 相关字段 |
|----|-----------|--------------|-------------------|-------------------|
| 配置 config | HotUpdate `config_patch_manifest` | Step1 配置导出 | 不含（Step3 剥离 config） | `config_manifest_url`、`config_relative_path` |
| 代码 code | HybridCLR `code_patch_manifest` | Step3 热更发布 | `code` | `code_manifest_url`、`code_relative_path` |
| 资源 resource | Addressables catalog | Step2 打包 + Step3 发布 | `resource` | `catalog_url`、`catalog_file_name`、`resource_relative_path` |
| 安装包 APK | 整包强更 | Step4 | 独立 `APK_BUILD_ENABLED` | `force_update`、`apk_url` |

版本组模板 / VC 行 bootstrap 门禁字段：

| 字段 | 说明 |
|------|------|
| `resource_server_url` | OSS 根 URL |
| `catalog_file_name` | 默认 `catalog_{version_name}.bin` |
| `min_client_version` | 最低可热更客户端版本 |
| `rollout_percentage` | 灰度 0–100 |
| `force_update` | 强制整包更新 |
| `is_revoked` | 撤销该 VC 热更 |

预览接口：`GET /admin/projects/{project_id}/versions/{version_id}/runtime-preview`

## 四步管线 ↔ Jenkins 参数

| Step | pipeline 键 | Jenkins 参数 | 说明 |
|------|---------------|--------------|------|
| 0 构建环境 | `apk_build.*`, `jenkins_*` | `GIT_BRANCH`, `UNITY_VERSION`, `APP_NAME`, `OUTPUT_BASE_DIR`, `UNITY_PROJECT_PATH` | Jenkins 实例/Job 在版本记录顶层 |
| 1 配置导出 | `config_export.enabled` | `CONFIG_EXPORT_ENABLED` | Step1 开关 |
| 1 | `config_export.remote_prefix` | `CONFIG_REMOTE_PREFIX`, `RELEASE_PROJECT_ROOT` | OSS 项目根 |
| 1 | `config_export.include_code` | `CONFIG_INCLUDE_CODE` | 配置包是否含代码 |
| 1 | `config_export.environment` | `CONFIG_ENVIRONMENT`, `RELEASE_ENVIRONMENT` | 发布环境 |
| 1 | `config_export.platform` | `CONFIG_PLATFORM`, `RELEASE_PLATFORM` | 平台 |
| 1 | `config_export.client_version` | `CONFIG_CLIENT_VERSION`, `RELEASE_VERSION` | 客户端版本 |
| 2 资源打包 | `resource_build.enabled` | `RESOURCE_BUILD_ENABLED` | Step2 开关 |
| 2 | `resource_build.provider` | `RESOURCE_PROVIDER` | Addressables 引擎 |
| 2 | `resource_build.scenario` | `RESOURCE_SCENARIO` | 场景方案 |
| 3 热更发布 | `hot_release.enabled` | `HOT_RELEASE_ENABLED` | Step3 开关 |
| 3 | `hot_release.release_targets` | `RELEASE_TARGETS` | `code` / `resource` 组合 |
| 3 | `hot_release.code_enabled` 等 | `RELEASE_CODE_*` | 代码包策略 |
| 3 | `hot_release.resource_enabled` 等 | `RELEASE_RESOURCE_*` | 资源包策略 |
| 3 | `hot_release.release_mode` | 计划 JSON + CLI 模式 | build / build-upload / upload 等 |
| 4 安装包 | `apk_build.enabled` | `APK_BUILD_ENABLED`, `RUN_BASE_APK_BUILD_FIRST` | 是否出 APK/IPA |

映射实现：[`commercial_release_plan.plan_to_jenkins_params`](portals/common/core/services/commercial_release_plan.py)、[`plan_defaults_from_pipeline`](portals/common/core/services/commercial_release_plan.py)。

发布快照：[`bundle_service.build_client_bootstrap_snapshot`](portals/common/core/services/release/bundle_service.py) 在 `publish_release_order` 写入完整 `bundle.client`。

## 产物路径（按 VC 自动推导，只读）

| 字段 | 用途 |
|------|------|
| `apk_path` | 本地 APK/IPA 相对路径 |
| `resource_path` | 资源包登记路径 |
| `config_path` | 配置包登记路径 |

运行时 OSS 相对路径由 `commercial_release_plan.build_runtime_resolve_paths` 按环境/渠道/平台/版本推导。

## URL section 参数

| section | Tab |
|---------|-----|
| `jenkins` | 构建环境 |
| `config_export` | 配置导出 |
| `resource_build` | 资源打包 |
| `hot_release` | 热更发布 |
| `artifact` | 安装包 |
| `client_policy` | 客户端更新策略 |

兼容别名：`pipeline` → `resource_build`（发布单旧链接）。

## 验收用例

1. **版本组配置管线模板** → 新建 VC → 路径/四步开关自动正确，**无需发布单改参**。
2. **改模板**（`edit_scope=version_group`）→ 同 `version_name + env + platform` 下已有 VC `pipeline` 同步更新，各 VC 路径按编号重算。
3. **新建发布单 STEP02** 仅展示 Jenkins/管线摘要；「配置版本组模板」跳转模板页，保存后返回发布单。
4. **发布单触发构建** 优先读 `version.pipeline`（`plan_defaults_from_pipeline`），不依赖 `payload.jenkins_params` 手填。
