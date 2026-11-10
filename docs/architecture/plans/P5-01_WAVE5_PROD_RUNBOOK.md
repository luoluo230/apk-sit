# P5-01 Wave 5 — 生产运维签字 Runbook

> **日期**：2026-11-10  
> **Plan**：[`P5-01_remaining_open_closure.md`](./P5-01_remaining_open_closure.md) §6  
> **队列**：[`OPS_SIGN_OFF_QUEUE.md`](./OPS_SIGN_OFF_QUEUE.md)  
> **规则**：`.cursor/rules/no-false-completion.mdc` — 本 runbook 准备包 **不等于** 生产 DONE。

本文档为运维逐步操作说明；优先闭环 **COMM-P0-1**、**W-P0-3**、**OPEN-2026-11-10-05**。其余 Wave 5 ID 见签字队列表。

---

## 0. 前置

| 项 | 说明 |
|----|------|
| 维护窗 | Portal 滚动发布或短暂 maintenance |
| Secret | 按 [`production_secrets.md`](../../runbooks/production_secrets.md) 填写生产 `.env`（**勿提交 git**） |
| PostgreSQL | 生产 `DATABASE_URL` 为 managed PostgreSQL（非 SQLite） |
| 证据 | 每步产物写入工单附件或本地 `docs/evidence/`（交付树已移出、gitignore）；勿依赖仓库内 evidence |

---

## 1. OPEN-2026-11-10-05 — 生产 fail-fast 运维签字

**升 DONE 门槛**：脱敏生产启动日志，证明 `APP_ENV=production` 下缺 Secret 拒绝启动；配置齐全后验证脚本 PASS。

### 1.1 本机预演（pre-prod，已可用于开发回归）

```powershell
# 仓库根
powershell -File scripts/verify_production_secrets.ps1 -ExpectFail
```

预期：`verify_production_secrets: fail-fast OK (as expected without secrets)`，exit 0。

```text
py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py
```

预期 JSON 中 `secrets_fail_fast.ok` 为 true（内存探针，非生产进程）。

### 1.2 生产步骤（运维）

1. **变更前**：确认生产 systemd/K8s/env **未**设置 `WEBHOOK_AUTH_DISABLED=1`。
2. **负向（脱敏）**：在**单实例金丝雀**上临时移除一项必填 Secret（如 `APK_SECRET`），尝试启动 Portal；捕获 stderr/日志片段，**涂掉**主机名/IP/租户信息，保留错误类文案（如 `missing required secrets`）。
3. **正向**：恢复全部 Secret 后执行：

```powershell
powershell -File scripts/verify_production_secrets.ps1
```

预期：`verify_production_secrets PASS`。

4. 正常启动 Portal；附启动时间戳与 `DATABASE_URL` 主机段（无口令）。

### 1.3 证据 JSON 字段（示例）

```json
{
  "gap_id": "OPEN-2026-11-10-05",
  "status": "DONE",
  "command": "powershell -File scripts/verify_production_secrets.ps1 (+ prod startup log redacted)",
  "exit_code": 0,
  "artifact_paths": ["docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-05.json"],
  "notes": "prod fail-fast log hash=...; verify PASS after secrets restored; signer=..."
}
```

在签字完成前，MASTER 保持 **BLOCKED**；仅有 pre-prod 不得写 `status: DONE`。

---

## 2. W-P0-3 — 生产 DATABASE_URL=PostgreSQL

**升 DONE 门槛**：生产运行时 SSOT 为 PostgreSQL；`require_production_database()` 在生产配置下不可回落 SQLite。

### 2.1 本机预演（pre-prod）

```text
py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py
```

检查输出 `secrets_fail_fast` 中 SQLite URL 被拒绝；若本地有 PG：

```powershell
$env:DATABASE_URL = '<local postgres url>'
py -3 portals/common/core/scripts/db_readiness_check.py --require-postgres
```

### 2.2 生产步骤（运维）

1. 确认生产 env：`DATABASE_URL` 以 `postgresql://` 或 `postgres://` 开头（工单仅记录 host/dbname）。
2. 在维护窗外或发布后执行：

```powershell
$env:DATABASE_URL = '<production connection string>'
py -3 portals/common/core/scripts/db_readiness_check.py --require-postgres
cd portals/common/core
py -3 -m pytest tests/test_project_registry.py tests/test_project_repo_concurrency.py -q
```

3. 若尚未 cutover，先完成 [`OPEN-2026-11-10-01`](#4-open-2026-11-10-01--pg-cutover-可选同窗) 再签 W-P0-3。

### 2.3 证据

- `docs/evidence/YYYY-MM-DD/W-P0-3.json`
- 附脱敏 `db_readiness_check` stdout 与 Portal `/health` 探针结果

**禁止**：仅凭本地 `p3_03` 将 MASTER `W-P0-3` 标 DONE。

---

## 3. COMM-P0-1 — 生产 Secret + PG 多 worker

**升 DONE 门槛**：生产 ≥2 worker，共享 PostgreSQL，跨实例可见同一 `release_order`（或等价 registry 行）。

### 3.1 本机预演（pre-prod）

```text
py -3 portals/common/core/scripts/wave_a_pg_multi_worker_gate.py
```

预期：`multi_worker_read.ok` true；`COMM-P0-1.json` 可为 **PARTIAL**（脚本内 `remaining_for_full_done` 已说明）。

引用父检查：

```text
py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py
```

### 3.2 生产步骤（运维）

1. 确认 **W-P0-3** / **OPEN-2026-11-10-05** 生产证据已就绪或同窗执行。
2. 部署 Portal **至少 2 个 worker**（Waitress/gunicorn 等多进程或多副本），环境变量一致（尤其 `DATABASE_URL`、Secret）。
3. 滚动发布后：
   - 通过任一 worker 创建测试 release_order（或运维指定冒烟 API）；
   - 从**另一 worker** 只读查询/接口确认同一 `id` 可见。
4. 记录：worker 数、镜像/tag、发布单号、脱敏 order id。

### 3.3 证据

```json
{
  "gap_id": "COMM-P0-1",
  "status": "DONE",
  "command": "production multi-worker deploy + cross-instance read smoke",
  "notes": "worker_count=...; order_id=wo-***; postgres_host=..."
}
```

本地 `wave_a_pg_multi_worker_gate.py` **不得**单独支撑 `status: DONE`。

---

## 4. OPEN-2026-11-10-01 — PG cutover（可选同窗）

详见 [`postgres_migration.md`](../../runbooks/postgres_migration.md)。

```powershell
py -3 portals/common/core/scripts/migrate_sqlite_to_postgres.py --dry-run --report D:\migration-evidence\sqlite-inventory.json
# 审批后
py -3 portals/common/core/scripts/migrate_sqlite_to_postgres.py --apply --database-url $env:DATABASE_URL --report D:\migration-evidence\postgres-migration.json
```

备份：

```powershell
powershell -File scripts/Backup-PortalData.ps1 -DatabaseUrl $env:DATABASE_URL -RequirePostgres -OutputDir D:\backups\apk-site
```

证据：`OPEN-2026-11-10-01.json`、`OPEN-2026-11-10-02.json`（SSOT+备份与 W-P0-3 可交叉引用）。

---

## 5. 关联 Wave 5 项（简表）

| ID | 生产动作摘要 | 主要脚本 |
|----|--------------|----------|
| GAP-P0-01-SEC-02 / W-P0-1 | 弱口令扫描 + 凭据审计 | `production_secret_gate.py` |
| W-P0-2 | Webhook HMAC/IP 签字 | runbook + pytest 路径见 P0-01 |
| W-P0-5 | 无 dev cluster token | `verify_production_secrets.ps1` |
| GAP-P0-02-S6-01 / OPEN-2026-11-10-04 | CI compose pytest | `postgres_compose_pytest_gate.py` |

完整命令列见 [`OPS_SIGN_OFF_QUEUE.md`](./OPS_SIGN_OFF_QUEUE.md)。

---

## 6. 收工检查（运维）

- [ ] 三个优先 ID 的生产证据 JSON 已落盘且 **脱敏**
- [ ] [`OPEN_ITEMS_MASTER.md`](./OPEN_ITEMS_MASTER.md) 仅在实际生产证据后改 DONE
- [ ] 签字人从本表 / 工单可追溯到命令与时间戳
- [ ] 未将 pre-prod `PARTIAL` 证据误标为生产 `DONE`

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-11-10 | Wave 5 生产签字 runbook 初版（P5-01 准备包） |
