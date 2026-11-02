# 构建管线 — 环境×渠道

| 项 | 值 |
|---|---|
| 入口粒度 | 环境 × 渠道（平台在第 1 步选择） |
| 运行 URL | `/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/build` |
| BFF API | `GET /api/projects/{pid}/environments/{env}/channels/{channel_id}/build-journey` |
| 模板 | `project_channel_build_journey.html` |

## 六步模型

| 步 | 名称 | 完成条件 |
|----|------|----------|
| 1 | 选择平台 | `platform` query 已选 |
| 2 | 检查管线 | `pipeline_ready=true` |
| 3 | 选择 VersionCode | `version_id` 已选 |
| 4 | 触发构建 | 调用 quick-build / request_build |
| 5 | 监控构建 | `building` → 轮询 build status + **打包步骤检测** |
| 6 | 产物验收 | `artifacts_ready` 或 apk_status=found |

## 打包步骤检测（监控面板）

按本次构建实际启用的 Jenkins 商业流水线拆分（Android / 后续 iOS 自动打包共用检测面板）：

| 检测步 | 平台 | 条件 | 标记 |
|--------|------|------|------|
| 环境准备 | Android/iOS | 始终 | `[阶段 0]` |
| 配置导出 | Android/iOS | `CONFIG_EXPORT_ENABLED` | `[阶段 1]` |
| 资源打包 | Android/iOS | `RESOURCE_BUILD_ENABLED` | `[阶段 2]` |
| 热更发布 | Android/iOS | `HOT_RELEASE_ENABLED` | `[阶段 3]` |
| APK 打包 | Android | `APK_BUILD_ENABLED` | `[阶段 4]` |
| iOS Xcode 导出 | iOS | `IOS_BUILD_ENABLED` | `[阶段 5]` |
| IPA 归档导出 | iOS | `IOS_BUILD_ENABLED` | `[阶段 6]` |
| IPA 落盘/OSS | iOS | `IOS_BUILD_ENABLED` | `[阶段 7]` |
| TestFlight 上传 | iOS | `EXTERNAL_UPLOAD_TESTFLIGHT` | `[阶段 8]` |

**进度来源（优先推送）**  
1. Jenkins 脚本 `_pipeline_push_build_step` → `POST /api/internal/jenkins/build-step`（近实时）  
2. 回退：解析控制台 `[阶段 N]` / `Step N`  

状态色：绿=完成（流动动画）/ 蓝=进行中 / 红=失败 / 灰=手动停止。  
每步「查看日志」→ 构建与产物工作台（`build-history?build_number=&open_log=1&step=`）。

API：`build-events` / journey BFF 的 `latest_build.detection_steps`（`jenkins_step_detection.py` + `jenkins_step_push_store.py`）。

## 跳转关系

- 未配置管线 → build-config（`?from=build-journey`）
- 监控日志 → build-history scoped（步骤检测可带 `step` + `open_log=1`）
- 验收完成 → 「进入发版流程」链到 release journey

## 禁止

- 不在构建流程页内执行 precheck / publish
- 不以发布单详情作为主构建界面
