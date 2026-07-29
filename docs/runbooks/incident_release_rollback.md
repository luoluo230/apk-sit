# 发布事故与自动回滚 Runbook（P2-03）

当 **verify 失败**、**bootstrap smoke 失败** 或 **publish 失败** 时，Portal 会通过统一出站 webhook 发送通知，并在策略允许时自动回滚。

---

## 1. 通知渠道配置

| 变量 | 说明 |
|------|------|
| `NOTIFY_WEBHOOK_URL` | 通用 JSON webhook（优先）；未设置时回退到系统 `webhook_url` |
| `NOTIFY_SIGNING_SECRET` | HMAC 签名密钥（Header: `X-Signature-SHA256`） |
| `WEBHOOK_FEISHU_URL` / 系统配置 | 飞书卡片通知 |
| `WEBHOOK_DINGTALK_URL` / 系统配置 | 钉钉 Markdown 通知 |

支持事件：

- `verify_failed`
- `bootstrap_smoke_failed`
- `publish_failed`
- `approval_sla_timeout`
- `auto_rollback_executed`

---

## 2. 自动回滚策略

环境默认（可在项目环境 `release_policy` 覆盖）：

| 环境 | `auto_rollback_on_verify_fail` |
|------|-------------------------------|
| development / testing | `false` |
| staging | `true` |
| production | `false`（仅通知，需人工确认回滚） |

verify 失败且策略为 `true` 时：

1. 查找同 scope 上一成功 Bundle 的发布单
2. 调用 `rollback_release_order`
3. 发送 `auto_rollback_executed` 通知

---

## 3. 手动回滚

Portal：**发布单详情 → 回滚**  
API：`POST /api/projects/{id}/release-orders/{order_id}/actions` body `{ "action": "rollback" }`

回滚后请复验：

1. `runtime-bootstrap` 指向旧 Bundle
2. 客户端冷启动 + 热更拉取正常

---

## 4. Metrics

```bash
curl -s http://127.0.0.1:5003/api/internal/metrics/release
```

指标：

- `release_orders_total{status}`
- `release_verify_failures_total`
- `release_publish_failures_total`
- `bootstrap_smoke_duration_seconds_*`

Prometheus scrape 示例见 `docs/grafana/README.md`。

---

## 5. Portal 健康看板

**项目总览 → 发布健康（近 7 天）**

- 发布成功率（verified / 失败事件）
- verify / publish 失败列表（来自 `release_order_events`）

---

## 6. 本地验证

```powershell
Set-Location e:\web\apk-site\portals\common\core
py -m unittest tests.test_observability_incident_loop -v
```

模拟 verify fail webhook（需本地 Portal 运行且配置 `NOTIFY_WEBHOOK_URL`）：

1. 创建发布单并 publish
2. 人为让 smoke URL 404 或调用 verify with bad artifacts
3. 检查 webhook 收到 `verify_failed` payload
4. staging 环境应自动回滚并收到 `auto_rollback_executed`
