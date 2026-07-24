# P1-02：项目 onboarding 向导

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 2 周 |
| 依赖 | P0-02 建议（project_repo API 稳定） |
| 评审项 | 初始化 8–12 步 → 1 向导；加渠道 5 步 → 1 API |

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
    {"label": "启动 Dev Runtime", "url": "/admin/projects/GomeKu/ops/runtime"},
    {"label": "打开 Build Journey", "url": "/admin/projects/GomeKu/channels/1001/build"}
  ]
}
```

**原子性**：任一步失败则整单 rollback（DB transaction + repo undo）。

---

## 4. 分步实施

### Step 1：Service 编排层（3 天）

**动作**

1. 新建 `services/admin/project_onboarding_service.py`：
   - `onboard_project(payload, actor) -> OnboardResult`
   - 内部顺序调用：`create_project` → assign channels/platforms → env defs → `create_version_group` → `create_version` → `ensure_scopes_for_project`
2. 默认 pipeline 从 `project.build_config` + 全局模板 `data/onboarding_defaults.json`（新建）

**改文件**

- `services/admin/project_onboarding_service.py`
- `data/onboarding_defaults.json`
- `tests/test_project_onboarding.py`

**验收**

- [ ] API 单测：mock Jenkins，断言 DB 状态完整
- [ ] 失败 mid-flight 无脏 project 残留

---

### Step 2：渠道原子添加 API（2 天）

**动作**

1. `POST /api/admin/projects/{id}/channels/assign` 扩展为原子：
   - project.channels[]
   - 各 env delivery_scope
   - 可选：为已有 version_group 复制 VC 行
2. 与 onboarding 共用 `channel_assignment_service.py`

**验收**

- [ ] 加渠道后 Journey 可见新 delivery line
- [ ] HotUpdateConfigSyncCli 映射文档链接在响应 `docs/client_bootstrap_contract.md`

---

### Step 3：UI 向导（4 天）

**动作**

1. 新页 `/admin/projects/new/wizard`（或 modal 多步）
2. 步骤：基本信息 → Git/Unity → 渠道/平台 → 环境 → Jenkins → 首版本 → 确认
3. 静态 `project_onboarding.js` + 复用现有 i18n

**设计 spec**：可引用 `docs/design_specs/project_list_p01.md` 风格，单独 checklist 可选

**验收**

- [ ] Browser：走完向导 → Build Journey 可点 quick-build（Jenkins 在线前提下）
- [ ] JS syntax gate pass

---

### Step 4：文档与 DevStack 集成（1 天）

**动作**

1. `Start-DevStack.ps1` 可选 `-OnboardProject` 调用 API seed GomeKu
2. README / runbook 链接向导 URL

**验收**

- [ ] 新 clone 仓库按 runbook 30 分钟内触发构建（熟练者）

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

- [ ] `POST .../onboard` 生产可用（权限：admin / project create）
- [ ] UI 向导 7 步内完成
- [ ] pytest + 手动 smoke 文档写入 `docs/runbooks/project_onboarding.md`
