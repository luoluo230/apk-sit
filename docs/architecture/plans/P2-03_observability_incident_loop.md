# P2-03：观测与事故闭环

| 项 | 值 |
|----|-----|
| 优先级 | P2 |
| 预估 | 2–4 周 |
| 依赖 | P2-01 可选（server deploy 事件） |
| 评审项 | Prod 事故回滚、无自动告警 |

---

## 1. 目标

发布 **verify 失败** 或 **bootstrap smoke 失败** 时：自动通知 + 可选自动 rollback；Ops Agent 指标进入统一看板（Grafana 或 Portal 内置）。

---

## 2. 范围

**In**

- verify / bootstrap smoke 失败 webhook（飞书/钉钉/Slack）
- 策略：`auto_rollback_on_verify_fail`（默认 production=off, staging=on 可配）
- ReleaseOrder 事件流：`release_order_events` 导出 metrics
- Agent Prometheus scrape 文档化（`docs/grafana/README.md` 扩展）

**Out**

- 全链路 APM（SkyWalking 等）
- 客户端 crash 上报平台

---

## 3. 分步实施

### Step 1：出站通知统一（3 天）

**动作**

1. `services/notify/outbound_webhook.py` — 已有 approval 通知扩展
2. 事件：`verify_failed`, `publish_failed`, `bootstrap_smoke_failed`, `approval_sla_timeout`
3. env：`NOTIFY_WEBHOOK_URL`, `NOTIFY_SIGNING_SECRET`

**改文件**

- `services/release/order_publish_flow.py` — verify 失败触发
- `order_publish_flow.run_bootstrap_smoke_for_order`

**验收**

- [ ] 模拟 verify fail → 测试 webhook 收到 payload

---

### Step 2：自动回滚策略（4 天）

**动作**

1. `release_policy_service` 增加 `auto_rollback_on_verify_fail: bool`
2. verify 失败且 policy true → 调 `rollback_release_order` + 通知
3. 审计 log + 人工 confirm 模式（production 默认 confirm-only：只通知不自动 rollback）

**验收**

- [ ] staging 环境 e2e：verify fail → rollback → bootstrap 指旧 bundle

---

### Step 3：Metrics 导出（3 天）

**动作**

1. `GET /api/internal/metrics/release` — Prometheus text format
   - `release_orders_total{status}`
   - `release_verify_failures_total`
   - `bootstrap_smoke_duration_seconds`
2. Agent 已有 metrics → 文档合并 scrape config

**改文件**

- `services/monitor/release_metrics.py`（新建）
- `docs/grafana/README.md`

**验收**

- [ ] Prometheus scrape 成功（local docker）

---

### Step 4：Portal 发布健康看板（可选，1 周）

**动作**

1. 项目 Overview 增加「近 7 天发布成功率」「verify 失败列表」
2. 数据来自 `release_order_events` SQL 聚合

**验收**

- [ ] Overview 显示真实 DB 数据

---

## 4. 完成定义（DoD）

- [ ] 至少 1 种 notify channel 生产可用
- [ ] auto rollback 策略可配置且默认 Prod 安全
- [ ] metrics endpoint + grafana doc
- [ ] runbook `docs/runbooks/incident_release_rollback.md`
