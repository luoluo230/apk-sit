# Portal 部署拓扑决策（GAP-P0-02-PRE-02）

本文档记录 Dev Portal 推荐的进程拓扑与扩容前提，供运维与 Plan Closure 签字使用。

## 当前默认（Dev / 单实例）

| 组件 | 默认形态 | 说明 |
|------|----------|------|
| Portal (Flask) | 单 worker / 单进程 | `Start-DevStack.ps1` 本地开发 |
| 数据真源 | SQLite (`data/release_orders.db` 等) | 适合单机 DevStack |
| 灰度调度 | 进程内后台线程 | `services/startup.py` 每 60s tick |
| Jenkins | 可选 sidecar | 8082 实例，非 Portal 强依赖 |

## 生产推荐（尚未全面 E2E 验证）

| 决策 | 推荐 | 阻塞项 |
|------|------|--------|
| DB 真源 | PostgreSQL 单主 | GAP-P0-DB-01 |
| Portal worker | 1 worker 直到 PG 迁移完成 | GAP-P0-OPS-01 |
| 多 worker | 仅在 PG + 会话外置后启用 | GAP-P0-DB-02 |
| 文件上传/APK | 对象存储 + 无本地竞态 | 与 DB 决策绑定 |

## 读写一致性假设

- **SQLite 单 worker**：A 进程写入对同进程读取立即可见；不支持多 worker 并发写。
- **PostgreSQL（目标）**：所有 Portal worker 共享同一连接池；release_order 状态以 DB 为准。
- **JSON 项目配置**（`data/projects.json` 等）：仍可能被多 worker 读到旧快照；生产应逐步迁入 repo API / DB。

## 签字检查项

1. 目标环境已选定上表「默认」或「生产推荐」列。
2. 若启用多 worker，已完成 GAP-P0-02-S2/S3 并发验证。
3. 备份策略见 `docs/runbooks/production_backup_restore.md`，且包含 DB 真源路径。

## 相关门禁

```bash
cd portals/common/core
py -3 scripts/plan_closure_gate.py
py -3 scripts/production_secret_gate.py
```
