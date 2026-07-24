# 生产环境 Secret 清单

> Plan: P0-01 Step 1  
> 适用：`APP_ENV=production` 或对外暴露的预发环境

## 必填 Secret（Portal 启动门禁）

| 环境变量 | 用途 | 配置位置 |
|----------|------|----------|
| `APP_ENV` | 设为 `production` 启用门禁 | 部署 env / systemd / K8s |
| `APK_SECRET` 或 `FLASK_SECRET_KEY` | Flask Session、CSRF | **禁止**依赖 `data/secret.key` 自动生成 |
| `JENKINS_BUILD_WEBHOOK_SECRET` | Jenkins build-complete HMAC | Portal `.env` + Jenkins `.apk-site-env` |
| `APPROVAL_WEBHOOK_SECRET` | 外部审批 webhook 入站 | Portal `.env` |
| `BUILD_NODE_WEBHOOK_SECRET` | 构建节点 heartbeat/register | Portal `.env` + Agent 安装脚本 |
| `CLUSTER_RELAY_TOKEN` | game-server 集群 relay 鉴权 | Portal `.env` + game-server 进程 env |

可选按 provider 覆盖：`APPROVAL_WEBHOOK_SECRET_FEISHU`、`APPROVAL_WEBHOOK_SECRET_DINGTALK`。

## Jenkins 凭据（非 Portal Session）

| 环境变量 | 用途 | 说明 |
|----------|------|------|
| `JENKINS_USER` / `JENKINS_TOKEN` | 调用 Jenkins API | 推荐 API Token，见 `jenkins_credentials.json` |
| `JENKINS_DEFAULT_PASSWORD` | 新建实例 init.groovy 注入 | **无代码默认值**；未配置则跳过 init 脚本 |

## 游戏服（game-server）

| 环境变量 | 用途 |
|----------|------|
| `CLUSTER_RELAY_TOKEN` | 集群 relay 鉴权；**不要**写入 `cluster.json` 提交仓库 |

Dev 栈：`scripts/Start-DevStack.ps1` 注入开发用 token。

## Internal Webhook 网络

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `INTERNAL_WEBHOOK_IPS` | `127.0.0.1,::1` | 允许调用 internal API 的来源 IP/CIDR |

## 开发环境专用（禁止生产文档化）

| 环境变量 | 说明 |
|----------|------|
| `PORTAL_DEV_ADMIN_PASSWORD` | 本地 Portal 首次 seed admin 密码（无代码默认值） |
| `WEBHOOK_AUTH_DISABLED=1` | 仅 `APP_ENV!=production` 时跳过 HMAC（本地调试） |

## 配置示例（.env.production 片段）

```bash
APP_ENV=production
APK_SECRET=<random-64-hex>
JENKINS_BUILD_WEBHOOK_SECRET=<random>
APPROVAL_WEBHOOK_SECRET=<random>
BUILD_NODE_WEBHOOK_SECRET=<random>
CLUSTER_RELAY_TOKEN=<random>
INTERNAL_WEBHOOK_IPS=10.0.0.0/8,127.0.0.1
JENKINS_USER=ci-bot
JENKINS_TOKEN=<jenkins-api-token>
```

## 启动验证

```bash
# 应失败（exit 非 0）
APP_ENV=production python -c "from config import require_production_secrets; require_production_secrets()"

# 开发应通过
APP_ENV=development python -c "from config import require_production_secrets; require_production_secrets(); print('ok')"
```

## 相关文档

- [`jenkins_local.md`](./jenkins_local.md) — Jenkins webhook 与密钥同步
- [`production_backup_restore.md`](./production_backup_restore.md) — 备份含 Secret 文件权限说明
