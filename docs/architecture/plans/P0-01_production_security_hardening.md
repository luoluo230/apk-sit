# P0-01：生产安全加固

| 项 | 值 |
|----|-----|
| 优先级 | P0 — 上线前阻断 |
| 预估 | 1–2 周 |
| 依赖 | 无 |
| 评审项 | W-P0-1, W-P0-2, W-P0-5 |
| 仓库 | apk-site, maclient/game-server |

---

## 1. 目标

消除默认弱凭据、收紧 Webhook/Internal 鉴权、生产环境 cluster relay token 外置，使平台 **可安全暴露在内网/VPN 外**（仍非完整 SaaS 多租户）。

---

## 2. 范围

**In**

- Jenkins / Portal 默认密码与 dev token
- Internal webhook（Jenkins build-complete、approval、build-node heartbeat）
- CSRF 豁免策略收紧
- 备份与 Secret 注入 runbook

**Out**

- 完整 SSO / OIDC（另开 Plan）
- mTLS 全链路（可选 Step 5 增强）

---

## 3. 分步实施

### Step 1：Secret 清单与启动门禁（2 天）

**动作**

1. 新建 `docs/runbooks/production_secrets.md`，列出所有 Secret 键：

| Secret | 当前位置 | 生产要求 |
|--------|----------|----------|
| `FLASK_SECRET_KEY` | `config.py` / env | 必须 env 注入，禁止空/默认 |
| `JENKINS_DEFAULT_PASSWORD` | `config.py:176` 默认 `admin123` | **删除默认值**；未配置则 Jenkins 管理页只读提示 |
| `JENKINS_WEBHOOK_SECRET` | pipeline / internal route | HMAC 必填 |
| `APPROVAL_WEBHOOK_SECRET` | approval webhook | 必填 |
| `BUILD_NODE_SHARED_SECRET` | internal build nodes | 必填 |
| `CLUSTER_RELAY_TOKEN` | `cluster.json` Metadata | 移出 JSON，env 注入 |

2. 在 `config.py` 增加 `require_production_secrets()`：`APP_ENV=production` 时缺任一 Secret **启动失败**（fail-fast）。

**改文件**

- `portals/common/core/config.py`
- `portals/common/core/app_new.py`（启动时调用校验）
- `docs/runbooks/production_secrets.md`（新建）

**验收**

- [x] `APP_ENV=production` 且无 `FLASK_SECRET_KEY` → 进程 exit 非 0
- [x] 日志无 `admin123` 字面量
- [x] `settings.example.json` 注释标明必填 Secret

---

### Step 2：去掉 Jenkins 默认密码（1 天）

**动作**

1. `JENKINS_DEFAULT_PASSWORD` 改为空字符串默认；`jenkins_manager` 创建实例时若未配置则 **不写入密码**，UI 提示「请通过 env 或 credentials 文件配置」。
2. 文档更新 `docs/runbooks/jenkins_local.md`：dev 可用 `.env`，prod 禁止默认。

**改文件**

- `portals/common/core/config.py`
- `portals/common/core/services/jenkins_manager.py`
- `data/jenkins_instances/` 示例不含明文密码

**验收**

- [x] 新装 Jenkins 实例无默认 `admin123`
- [x] 现有 dev 栈仍可通过 `.env` 启动

---

### Step 3：Webhook HMAC 统一（3 天）

**动作**

1. 新建 `services/security/webhook_auth.py`：
   - `verify_hmac_signature(body, header, secret)` 
   - 支持 `X-Signature-SHA256` + timestamp 防重放（5 分钟窗口）
2. 应用到：
   - `routes/internal_jenkins*.py` build-complete
   - approval webhook routes
   - `routes/internal_build_nodes.py` heartbeat/register
3. Jenkins pipeline 末尾 curl 增加签名头（更新 `commercial_pipeline_common.sh`）。

**改文件**

- `portals/common/core/services/security/webhook_auth.py`（新建）
- `portals/common/core/routes/internal_*.py`
- `jenkins-clone/scripts/commercial_pipeline_common.sh`
- `portals/common/core/tests/test_webhook_auth.py`（新建）

**验收**

- [x] 无签名 POST build-complete → 401
- [x] 正确签名 → 200
- [x] pytest 新增 ≥4 case

---

### Step 4：CSRF 策略收紧（2 天）

**动作**

1. **保留** CSRF：所有 browser form POST（admin 登录、项目设置表单）。
2. **移除** 整 Blueprint exempt；改为：
   - Delivery/Ops **JSON API**：`Content-Type: application/json` + session cookie **仍校验 CSRF token**（前端已有 token 注入则不变）
   - Internal routes：**不用 CSRF**，改用 Step 3 HMAC + IP allowlist（`INTERNAL_WEBHOOK_IPS` env，默认 `127.0.0.1`）
3. 更新 `app_new.py`：仅 `internal_*` blueprint exempt CSRF。

**改文件**

- `portals/common/core/app_new.py`
- `portals/common/core/static/*` 确认 AJAX 带 CSRF header

**验收**

- [x] Delivery JSON API 无 token → 400/403
- [x] Internal webhook 无 HMAC → 401（非 CSRF 问题）
- [x] 现有 release journey e2e smoke 仍 pass

---

### Step 5：game-server cluster token 外置（1 天）

**动作**

1. `cluster.json` 中 `ClusterRelayToken` 改为占位符 `${CLUSTER_RELAY_TOKEN}` 或移除，由 `GlobalConfig` / 启动脚本从 env 读取。
2. `Start-DevStack.ps1` 注入 dev token；生产 runbook 要求独立 token。
3. Portal `_sync_cluster_to_agents` 同步时不覆盖生产 token（只同步 host/port/role）。

**改文件**

- `maclient/game-server/config/cluster.json`（或 template + 生成脚本）
- `maclient/game-server/.../GlobalConfig` 读取 env
- `scripts/Start-DevStack.ps1`

**验收**

- [x] repo 内无生产可用 relay token 明文
- [x] dev 栈一键启动仍通 Gateway

---

### Step 6：备份 runbook（1 天）

**动作**

1. 新建 `docs/runbooks/production_backup_restore.md`：
   - 每日：`apk_site.db` + `data/projects.json` + `data/jenkins_instances/`
   - 每周：全 `data/` 目录
   - OSS：bucket 生命周期与 cross-region（运维填具体 bucket）
2. 提供 `scripts/Backup-PortalData.ps1` 骨架（打包 + 可选上传）。

**验收**

- [x] runbook 可被运维按步骤执行
- [x] 备份脚本在本机 dry-run 成功

---

## 4. 测试与门禁

```bash
cd portals/common/core
python -m pytest tests/test_webhook_auth.py tests/test_internal_jenkins_webhook.py -q
python -m compileall config.py app_new.py services/security/
```

CI 新增 job：`production_secret_gate` — 扫描 repo 中 `admin123`、`ma-cluster-relay-dev` 明文（允许 test/fixture 目录 exclude）。

---

## 5. 回滚

- Secret 校验可通过 `APP_ENV=development` 跳过（仅 dev）
- Webhook HMAC：env `WEBHOOK_AUTH_DISABLED=1` 临时关闭（prod 禁止文档化）

---

## 6. 完成定义（DoD）

- [x] 6 个 Step 验收项全勾
- [x] runbook 两份已提交
- [ ] 评审项 W-P0-1 / W-P0-2 / W-P0-5 在 issue 中关闭并链到本 Plan
