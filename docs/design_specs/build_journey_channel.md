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
| 5 | 监控构建 | `building` → 轮询 build status |
| 6 | 产物验收 | `artifacts_ready` 或 apk_status=found |

## 跳转关系

- 未配置管线 → build-config（`?from=build-journey`）
- 监控日志 → build-history scoped
- 验收完成 → 「进入发版流程」链到 release journey

## 禁止

- 不在构建流程页内执行 precheck / publish
- 不以发布单详情作为主构建界面
