# Jenkins 本地实例 Runbook

> 面向 `data/jenkins_instances/*` 本地 Jenkins 副本的日常运维与发版联动。

## 目录约定

| 路径 | 说明 |
|------|------|
| `data/jenkins_instances/{port}/` | 单实例 `JENKINS_HOME` |
| `data/jenkins_instances/{port}/.apk-site-env` | 构建脚本 source 的环境变量 |
| `data/jenkins_instances/{port}/scripts/` | 商业流水线、归档脚本 |
| `data/jenkins_instances.json` | 实例注册表（id、port、jenkins_home） |

## Git 忽略（运行时噪声）

以下路径不应提交（已在根 `.gitignore` 声明）：

- `data/jenkins_instances/**/queue.xml*`
- `data/jenkins_instances/**/builds/`
- `data/jenkins_instances/**/.owner`

若历史上已跟踪，可用 `git rm --cached` 移除索引后保留本地文件。

## 构建完成 Webhook

Jenkins 流水线结束后会 `POST /api/internal/jenkins/build-complete`：

```json
{ "instance_id": "<uuid>", "build_number": 123 }
```

请求头：`X-Jenkins-Signature: <hmac-sha256-hex>`（body 原始 JSON 的 HMAC）。

### 密钥

- 优先：`JENKINS_BUILD_WEBHOOK_SECRET`
- 回退：`APK_SECRET`（与 Flask session 同源）

在 apk-site `.env` 与 Jenkins 实例环境（`.apk-site-env` 或 Job 注入）中保持一致。

### 实例 ID 解析

流水线通过以下顺序解析 `instance_id`：

1. 环境变量 `JENKINS_INSTANCE_ID`
2. 读取 `data/jenkins_instances.json`，按 `jenkins_home` 路径匹配

建议在刷新实例环境时写入 `JENKINS_INSTANCE_ID`（`jenkins_manager.refresh_instance_env_and_scripts`）。

### 服务端行为

1. 校验 HMAC
2. 按 `instance_id` + `build_number` 查找 `status=building` 的 ReleaseOrder
3. 调用 `sync_release_order_build_status` → `artifacts_ready` 或 `build_failed`

仍保留 Journey/API 的 poll 作为兜底。

## 本地启动与刷新

1. 在管理端 **Jenkins 管理** 启动实例
2. apk-site 启动时会写 `data/apk/.apk-site-base-url` 与 `jenkins-clone/.apk-site-env`
3. 修改脚本后执行实例 **刷新环境**（或重启 apk-site 触发 overlay）

## 常见问题

| 现象 | 排查 |
|------|------|
| Webhook 401 | 检查 `JENKINS_BUILD_WEBHOOK_SECRET` / `APK_SECRET` 是否一致 |
| Webhook 200 但 `synced: false` | ReleaseOrder 不在 `building`，或 `payload.build_job_id` 与 Jenkins 编号不一致 |
| 构建 SUCCESS 但产物 missing | 查看 `build_finalize_failed` 事件；检查 `archive_apk_after_build.py` 日志 |
| queue.xml / builds 污染 git | 确认 `.gitignore` 规则；对已跟踪文件 `git rm --cached` |

## 相关代码

- Webhook 路由：`portals/common/core/routes/internal_jenkins.py`
- 构建同步：`portals/common/core/services/release/order_build_sync.py`
- 流水线脚本：`data/jenkins_instances/*/scripts/commercial_android_pipeline.sh`
