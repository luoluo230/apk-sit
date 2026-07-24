# P1-04：Dev 交付链路简化

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 1–2 周 |
| 依赖 | P1-01 部分（`runtime_orchestrator` 公开 API） |
| 评审项 | W-P1-4, Dev 发版 5–8 步 |

---

## 1. 目标

**development 环境**下：precheck/publish 前 **自动 ensure runtime**；Journey 一键「Dev 发版」串联 quick-publish；减少「Runtime 未启动」导致的硬失败。

---

## 2. 范围

**In**

- `release_policy_service` development 策略扩展
- precheck 前 auto-start runtime（仅 development）
- Journey UI：「启动 Runtime 并重试预检」合并为默认行为
- `quick_publish_delivery` 文档化推荐路径

**Out**

- production 自动启服（仍 block）
- 修改 publish 不依赖 runtime 的语义（Prod 仍必须 active runtime）

---

## 3. 分步实施

### Step 1：Runtime ensure API（2 天）

**动作**

1. 新建 `services/ops/runtime_orchestrator.py`（若 P1-01 未完成，先从 helpers 提取）：
   - `ensure_runtime_for_scope(project_id, env_key, topology_id, actor) -> {active, run_id, started: bool}`
2. 逻辑：无 active runtime → 调 Agent start → poll 30s → 返回 run_id
3. Idempotent：已有 active 则直接返回

**验收**

- [ ] 单元测试 mock Agent
- [ ] development env 可调通真实 DevStack（manual）

---

### Step 2：Precheck 集成（2 天）

**动作**

1. `precheck_release_order` 开头：
   - 若 `env_key==development` 且 policy `runtime_required=warn|auto`
   - 调用 `ensure_runtime_for_scope`
2. 失败则 precheck issue 含 `fix_action: start_runtime`（已有 O-03 可合并）

**改文件**

- `services/release/order_publish_flow.py`
- `services/release/release_policy_service.py`

**验收**

- [ ] Dev：Runtime STOPPED → precheck 自动启 → 通过（或明确 partial pass + 重试）
- [ ] Prod：仍 hard fail

---

### Step 3：Journey UX（2 天）

**动作**

1. Release Journey 预检失败卡片：默认按钮「自动启动 Runtime 并重试」（调 precheck API `?auto_ensure_runtime=1`）
2. 环境总览页显示 Runtime 状态 pill（已有 overview 可增强）

**改文件**

- `static/project_channel_release_journey.js`
- `routes/delivery/release_journey_api.py`（或现有 precheck route）

**验收**

- [ ] Playwright/manual：STOPPED → 一键恢复 precheck 绿

---

### Step 4：Quick-publish 路径文档 + CLI（1 天）

**动作**

1. `docs/runbooks/dev_daily_release.md`：
   - 推荐：`POST .../delivery-attempts/quick-publish` 参数表
   - 前置：Jenkins 在线、onboarding 完成（P1-02）
2. 可选：`scripts/Invoke-DevQuickPublish.ps1` 封装 curl

**验收**

- [ ] 新人按 runbook 完成 Dev 发版 ≤8 步（含装包）

---

## 4. 策略表（建议默认）

| env_key | runtime_required | auto_ensure_runtime |
|---------|------------------|---------------------|
| development | warn → **auto** | true |
| testing | warn | false |
| staging | block | false |
| production | block | false |

---

## 5. 完成定义（DoD）

- [ ] development precheck 不再因「仅 Runtime 停」单独阻断（在 Agent 可达前提下）
- [ ] Prod 行为不变
- [ ] runbook 已提交
- [ ] W-P1-4 用户体验项关闭
