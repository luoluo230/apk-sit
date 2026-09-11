# 生产数据备份与恢复

> Plan: P0-01 Step 6

## 备份范围

| 频率 | 路径 | 说明 |
|------|------|------|
| 每日 | `data/apk_site.db` | 迁移输入；仅 SQLite 部署时为主库 |
| 每日 | PostgreSQL custom dump | PostgreSQL 生产真源；由 `pg_dump` 生成 |
| 每日 | `data/projects.json` | 项目 JSON mirror（若启用双写） |
| 每日 | `data/jenkins_instances/` | Jenkins 实例配置（排除 `builds/` 运行时噪声） |
| 每周 | 整个 `data/` | 含 channels、versions、build_nodes mirror 等 |
| 按需 | OSS bucket | 由运维填写 bucket 与生命周期策略 |

**不要**将 `.env`、`jenkins_credentials.json`、`data/secret.key` 提交 git；备份文件应加密存储。

## DB 单一真源（P0-02 DoD）

| 存储 | 角色 | 说明 |
|------|------|------|
| `data/apk_site.db` | SQLite 部署的真源 / PostgreSQL 迁移输入 | projects/channels/versions registry、release_orders、infra_nodes、ops 表 |
| `data/projects.json` 等 | Mirror | 仅当 `SAVE_JSON_MIRROR=true`；恢复时以 `.db` 为准 |
| `build_nodes.json` | Mirror | `BUILD_NODES_JSON_MIRROR=1`；真源在 `infra_nodes` 表 |
| PostgreSQL | **生产真源** | `DATABASE_URL` 指向 PostgreSQL 后，必须用 `pg_dump` custom dump 备份；见 [`postgres_migration.md`](./postgres_migration.md) |

## 一键打包（Windows）

```powershell
powershell -File scripts/Backup-PortalData.ps1 -DryRun
powershell -File scripts/Backup-PortalData.ps1 -OutputDir D:\backups\apk-site
powershell -File scripts/Backup-PortalData.ps1 -DatabaseUrl $env:DATABASE_URL -RequirePostgres -OutputDir D:\backups\apk-site
```

## 恢复步骤（概要）

1. 停止 Portal / Waitress 进程。
2. 先运行 `Restore-PortalData.ps1` 验证 manifest 的 SHA-256。
3. 在维护窗口内，以 `-ConfirmRestore` 还原 SQLite 和（如存在）PostgreSQL dump。
4. 确认 `.env` Secret 与备份环境一致。
5. 启动 Portal，`GET /health` = ok。
6. 抽样：登录 Admin、打开 Release Journey、Jenkins 实例列表。

## 验证清单

- [x] 备份脚本 `-DryRun` 列出预期文件（见 `docs/evidence/` backup evidence）
- [x] 备份包可在另一目录解压且文件完整（`Backup-PortalData.ps1`）
- [x] 恢复后 pytest smoke / 手动 Journey 预检可用（`bootstrap_gate_e2e.py`）
