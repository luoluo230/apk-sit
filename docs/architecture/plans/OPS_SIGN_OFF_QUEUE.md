# 生产运维签字队列（Wave A/B 外阻）

> **日期**：2026-11-10（Wave 5 预演命令扩充）  
> **Plan**：[`P5-01_remaining_open_closure.md`](./P5-01_remaining_open_closure.md) §6  
> **含义**：下列 ID 的代码/本机证据已尽量齐备，**升 DONE 必须由运维/产品在真实（或签字级）生产环境补证据**。在签字前 MASTER 标为 **BLOCKED（ops）**，不得对外宣称完成。  
> **Wave 5 逐步 runbook**：[`P5-01_WAVE5_PROD_RUNBOOK.md`](./P5-01_WAVE5_PROD_RUNBOOK.md)  
> **交付树**：`docs/evidence/` 已移出可打包交付物；签字证据改附工单或本地忽略目录，勿依赖仓库内 evidence 路径。

---

## Wave 5 — 命令真源（复制自 P5-01 §1 / §6 + runbook）

| ID | 本机预演命令（pre-prod，≠ 生产 DONE） | 生产签字命令 / 动作 | 证据路径 | 签字仍缺 |
|----|--------------------------------------|---------------------|----------|----------|
| COMM-P0-1 | `py -3 portals/common/core/scripts/wave_a_pg_multi_worker_gate.py`（本地 PG 双进程；可写 `COMM-P0-1.json` **PARTIAL**） | 生产部署 ≥2 Portal worker，共享同一 `DATABASE_URL`；运维在变更单记录 worker 数、滚动发布窗口；跨实例读冒烟（脱敏 release_order id） | `docs/evidence/YYYY-MM-DD/COMM-P0-1.json` | 生产多 worker 部署说明 + 跨实例读签字 |
| GAP-P0-01-SEC-02 | `py -3 portals/common/core/scripts/production_secret_gate.py`；`powershell -File scripts/verify_production_secrets.ps1 -ExpectFail` | 在生产配置面（env + 已部署 `settings` 快照，**不含密钥明文**）重跑 secret gate；归档审计 JSON | `docs/evidence/YYYY-MM-DD/GAP-P0-01-SEC-02.json` | 生产 settings 无弱口令审计 JSON |
| W-P0-1 | 同上 `production_secret_gate.py` | 生产 Jenkins/Portal 凭据复核：`JENKINS_TOKEN` API Token、无 `admin123`；签字 JSON | `docs/evidence/YYYY-MM-DD/W-P0-1.json` | 生产配置审计 JSON |
| W-P0-2 | `cd portals/common/core` → `py -3 -m pytest tests/test_webhook_auth.py tests/test_internal_jenkins_webhook.py -q` | 生产 `.env` 已配齐 webhook HMAC + `INTERNAL_WEBHOOK_IPS`；各 webhook 试呼回执入库/工单 | `docs/evidence/YYYY-MM-DD/W-P0-2.json` | 生产 webhook HMAC/IP 配置记录签字 |
| W-P0-3 | `py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py`（内含 `require_production_database` 拒 SQLite） | 生产：`$env:DATABASE_URL='<managed PG>'` → `py -3 portals/common/core/scripts/db_readiness_check.py --require-postgres`；附**脱敏**启动日志（仅 host/dbname，无口令） | `docs/evidence/YYYY-MM-DD/W-P0-3.json` | 生产 DATABASE_URL=PG 运行证据 |
| W-P0-5 | `powershell -File scripts/verify_production_secrets.ps1`（`CLUSTER_RELAY_TOKEN` 不得为 dev 字面量） | 生产 cluster/game-server env 审计：`CLUSTER_RELAY_TOKEN` 随机且与 game-server 一致；**禁止** `Start-DevStack.ps1` | `docs/evidence/YYYY-MM-DD/W-P0-5.json` | 生产 cluster 配置复核（含外仓） |
| GAP-P0-02-S6-01 | `py -3 portals/common/core/scripts/postgres_compose_pytest_gate.py`（需 Docker） | CI nightly / 生产旁路：compose pytest 绿日志附 runner | `docs/evidence/YYYY-MM-DD/GAP-P0-02-S6-01.json` | GitHub nightly Docker PG pytest 绿 |
| OPEN-2026-11-10-01 | `py -3 portals/common/core/scripts/migrate_sqlite_to_postgres.py --dry-run --report <path>` | 按 [`postgres_migration.md`](../../runbooks/postgres_migration.md) 维护窗执行 `--apply`；工单附 dry-run + apply 报告路径 | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-01.json` | 生产 cutover 执行记录 |
| OPEN-2026-11-10-02 | `powershell -File scripts/Backup-PortalData.ps1 -DryRun` | 生产：`Backup-PortalData.ps1 -DatabaseUrl $env:DATABASE_URL -RequirePostgres`；证明 PG 为唯一 SSOT + 备份覆盖 | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-02.json` | 生产单一 SSOT 备份覆盖证明 |
| OPEN-2026-11-10-04 | 同 GAP-P0-02-S6-01 | CI live PG + 多 worker Portal job 绿；附 workflow run URL | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-04.json` | nightly Docker 绿 |
| OPEN-2026-11-10-05 | `powershell -File scripts/verify_production_secrets.ps1 -ExpectFail`；`py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py`（`secrets_fail_fast` 段） | 生产首次/变更启动：**脱敏**日志证明缺 Secret 时进程退出；全 Secret 配置后 `verify_production_secrets.ps1`（无 `-ExpectFail`）PASS | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-05.json` | 脱敏生产启动日志 |
| OPEN-2026-11-10-06 | `py -3 portals/common/core/scripts/promote_identity_e2e.py` | 生产环境晋级回放日志（artifact_id + sha256 一致） | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-06.json` | 生产晋级回放日志 |
| OPEN-2026-11-10-07 | 本地 NOTIFY capture（见 `OPEN-2026-11-10-07.json`） | 生产 NOTIFY webhook 试呼 + 回执 | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-07.json` | 生产 webhook 测试回执 |
| OPEN-2026-11-10-08 | `py -3 portals/common/core/scripts/bootstrap_gate_e2e.py`（本机 DONE） | CI `vars.RELEASE_GATE_BASE_URL` nightly 绿 | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-08.json` | CI nightly（生产签字队列残留项） |
| OPEN-2026-11-10-09 | `py -3 portals/common/core/scripts/server_release_devstack_e2e.py --base-url http://127.0.0.1:5003` | DevStack/CI workflow 绿 + 生产等价签字（若适用） | `docs/evidence/YYYY-MM-DD/OPEN-2026-11-10-09.json` | CI DevStack workflow 绿 |
| GAP-P2-03-E2E-03 | 本机 Prometheus `:9090` scrape DONE（见 MASTER） | （可选）staging/production Grafana 面板签字 | `docs/evidence/2026-11-10/GAP-P2-03-E2E-03.json` | 本机已闭环；生产面板可选 |
| GAP-P1-02-E2E-01 | 本机 DONE | — | `docs/evidence/2026-11-10/GAP-P1-02-E2E-01.json` | 已闭环，可移出队列 |
| GAP-P1-02-E2E-02 | `run_devstack_full_closure_e2e.ps1` PASS（本机 DONE） | — | `docs/evidence/2026-11-10/GAP-P1-02-E2E-02.json` | 已闭环，可移出队列 |
| GAP-P2-01-OUT-02 | 本机 DONE（GameServer-Build #1） | — | `docs/evidence/2026-11-10/GAP-P2-01-OUT-02.json` | 已闭环，可移出队列 |

---

## 速查（P5-01 §6 原文对照）

| ID | 命令/动作（Plan 摘要） | 产物 |
|----|------------------------|------|
| COMM-P0-1 | 生产多 worker 部署 + 跨实例读 | evidence JSON |
| GAP-P0-01-SEC-02 | 生产 settings 审计 | JSON |
| W-P0-1 | 同左 | JSON |
| W-P0-2 | webhook HMAC/IP 配置记录 | JSON |
| W-P0-3 | 确认 DATABASE_URL=PG | 日志 |
| W-P0-5 | 生产 cluster 无 dev token | 审计 |
| OPEN-2026-11-10-01 | cutover runbook 执行 | 记录 |
| OPEN-2026-11-10-02 | SSOT+备份演练 | 记录 |
| OPEN-2026-11-10-05 | 脱敏 fail-fast 启动日志 | 日志 |

---

## 签字后流程

1. 把证据 JSON 写入 `docs/evidence/YYYY-MM-DD/<ID>.json`（`status` 仅在为真生产证据时方可 `DONE`）。
2. 更新 [`OPEN_ITEMS_MASTER.md`](./OPEN_ITEMS_MASTER.md) 对应行 → `DONE`。
3. 从本表删除已签字 ID（或标注签字日期列）。

**禁止**：仅凭本机 `wave_a_pg_multi_worker_gate.py` / `-ExpectFail` 将 COMM-P0-1、W-P0-3、OPEN-2026-11-10-05 等标为 MASTER `DONE`。
