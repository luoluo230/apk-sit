# 部署拓扑决策（Plan P0-02 前置）

> 关闭 GAP：GAP-P0-OPS-01、GAP-P0-02-PRE-02

## Phase A — 当前强制（Postgres 切换前）

| 项 | 值 | 原因 |
|----|-----|------|
| 应用服务器 | **单进程 Waitress** | SQLite WAL + thread-local 连接；未验证跨进程一致性 |
| `threads` | **1** | 禁止多 worker 读写在 SQLite 阶段 |
| 数据库 | `data/apk_site.db` SQLite | 真源 |
| JSON mirror | `SAVE_JSON_MIRROR=true` 时双写 | 过渡恢复用，非真源 |
| 水平扩展 | **禁止** | 直到 Phase B multi-worker gate 通过 |

启动示例：

```powershell
cd portals/common/core
$env:WAITRESS_THREADS = "1"
py -3 scripts/run_admin_5003.ps1
```

## Phase B — Postgres 切换后

| 项 | 值 |
|----|-----|
| 数据库 | PostgreSQL via `DATABASE_URL` |
| `USE_SQLITE` | `false` |
| Waitress workers | **≥2** 允许（需跑 `test_multi_worker_registry` gate） |
| 迁移 | `migrate_sqlite_to_postgres.py` + row count 对账 |

## 验收 gate

```powershell
py -3 portals/common/core/scripts/sqlite_primary_gate.py          # Phase A
py -3 portals/common/core/scripts/postgres_compose_pytest_gate.py # Phase B
py -3 -m pytest portals/common/core/tests/e2e/test_multi_worker_registry.py -q
```

## 变更记录

| 日期 | 决策 |
|------|------|
| 2026-07-29 | 初版：Phase A 单 worker + SQLite 直至 PG gate 绿 |
