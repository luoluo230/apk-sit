# P1-02：项目 onboarding 向导

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 2 周 |
| 依赖 | P0-02 建议（project_repo API 稳定） |
| 评审项 | 初始化 8–12 步 → 1 向导；加渠道 5 步 → 1 API |
| 状态 | **Done**（2026-07-28） |

---

## 1. 目标

新项目从 **0 到可触发第一次 quick-build** 压缩为 **单一向导 + 单一 API**；熟练工程师 **≤30 分钟**，新人 **≤2 小时**。

---

## 2. 范围

**In**

- 创建 project + game_id/game_key
- 默认 `release_environments`（development/testing/staging/production 子集可勾选）
- 从全局 catalog 选渠道/平台白名单
- 创建首个 version_group + 默认 pipeline 模板（Android 四步）
- 绑定默认 Jenkins 实例（可选）
- 创建 development scope 行 + 首个 VersionCode 占位
- 拓扑 binding 占位（链接到 Ops 页）

**Out**

- 自动安装 Jenkins Agent（见 P1-05）
- 自动启动 GameServer（见 P1-04）

---

## 3. API 设计

### `POST /api/admin/projects/onboard`

**Request（示例）**

```json
{
  "name": "GomeKu",
  "slug": "gomeku",
  "git_url": "git@...",
  "unity_project_path": "E:/maclient",
  "channels": ["1001"],
  "platforms": ["android"],
  "env_keys": ["development", "testing"],
  "jenkins_instance_id": "8082",
  "seed_version_group": {
    "version_name": "1.0.0",
    "env_key": "development",
    "channel_id": "1001",
    "platform": "android"
  }
}
```

**Response**

```json
{
  "project_id": "GomeKu",
  "game_id": "...",
  "game_key": "...",
  "version_group_id": "...",
  "version_id": "...",
  "scope_ids": ["gomeku:development:1001:android"],
  "next_actions": [
    {"label": "配置 Jenkins 管线", "url": "/admin/projects/GomeKu/versions/..."},
    {"label": "启动 Dev Runtime", "url": "/admin/projects/GomeKu/ops?env_key=development"},
    {"label": "打开 Build Journey", "url": "/admin/projects/GomeKu/environments/development/channels/1001/build"}
  ]
}
```

**原子性**：任一步失败则 `_purge_onboard_artifacts` rollback（project + versions + scopes + manifest）。

---

## 4. 分步实施

### Step 1：Service 编排层（3 天） ✅

**动作**

1. `services/admin/project_onboarding_service.py` — `onboard_project(payload, actor)`
2. 默认 pipeline：`data/onboarding_defaults.json`
3. Scope bootstrap：`manifest_service.bootstrap_scopes_for_project`

**改文件**

- `services/admin/project_onboarding_service.py`
- `data/onboarding_defaults.json`
- `routes/admin/api_project_onboarding.py`
- `tests/test_project_onboarding.py`
- `repositories/admin/versions_repo.py`（`save_versions` → registry accessor）

**验收**

- [x] API 单测：断言 DB 状态完整
- [x] 失败 mid-flight 无脏 project 残留

---

### Step 2：渠道原子添加 API（2 天） ✅

**动作**

1. `POST /admin/projects/{id}/channels/assign` — `channel_assignment_service.assign_channels`
2. 更新 env delivery scope；可选 `copy_version_rows`

**验收**

- [x] 加渠道后 scope bootstrap 更新 delivery line
- [x] 响应含 `docs/client_bootstrap_contract`

---

### Step 3：UI 向导（4 天） ✅

**动作**

1. `/admin/projects/new/wizard`
2. 7 步：基本信息 → Git/Unity → 渠道/平台 → 环境 → Jenkins → 首版本 → 确认
3. `static/project_onboarding.js`

**验收**

- [x] JS syntax gate pass
- [ ] Browser E2E quick-build（需 Jenkins 在线；见 runbook 手动 smoke）

---

### Step 4：文档与 DevStack 集成（1 天） ✅

**动作**

1. `Start-DevStack.ps1 -OnboardProject [-OnboardPayloadFile]`
2. `docs/runbooks/project_onboarding.md`

**验收**

- [x] Runbook 已写入
- [ ] 新 clone 30 分钟 smoke（手动）

---

## 5. 与七层归属对齐

| 写入字段 | 归属层 | onboarding 是否写 |
|----------|--------|-------------------|
| git_url, unity_path | Project | ✅ |
| channels/platforms | Project | ✅ |
| release_environments | Environment | ✅ 默认模板 |
| pipeline_template | Version Group | ✅ 默认 Android 四步 |
| release_order | Release Order | ❌ 用户构建时创建 |

---

## 6. 完成定义（DoD）

- [x] `POST .../onboard` 生产可用（权限：`admin_required('projects')`）
- [x] UI 向导 7 步内完成
- [x] pytest + runbook `docs/runbooks/project_onboarding.md`
