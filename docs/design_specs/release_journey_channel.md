# 发版管线 — 环境×渠道

| 项 | 值 |
|---|---|
| 入口粒度 | 环境 × 渠道（平台在第 1 步选择） |
| 运行 URL | `/admin/projects/{project_id}/environments/{env_key}/channels/{channel_id}/release` |
| BFF API | `GET /api/projects/{pid}/environments/{env}/channels/{channel_id}/release-journey` |
| 模板 | `project_channel_release_journey.html` |

## 七步模型

| 步 | 名称 | 行为 |
|----|------|------|
| 1 | 选择平台 | Tab Android / iOS |
| 2 | 选择目标版本 | Tab：产物就绪 VC / 历史 Bundle / 当前线上 |
| 3 | 发版计划 | full 环境必填；minimal 可跳过 |
| 4 | 预检 | POST precheck |
| 5 | 发布操作 | 全量 / 灰度 / 指定 Bundle |
| 6 | 验证 | POST verify |
| 7 | 运维 | 回滚到 Bundle / 撤回下线 / 取消发布单 |

## 发布指定 / 撤回 / 回滚

| 操作 | API | 语义 |
|------|-----|------|
| 发布指定 Bundle | `POST .../scopes/{scope_id}/publish-bundle` | 激活历史 Bundle 为线上 |
| 回滚 | `POST .../scopes/{scope_id}/rollback` | 切换到指定历史 Bundle |
| 撤回下线 | `POST .../scopes/{scope_id}/unpublish` | 下线当前线上版本（非回滚） |

## 环境详情入口

渠道 group header 固定双按钮：**进入构建流程** / **进入发版流程**（始终可见，禁用时 tooltip 说明原因）。
