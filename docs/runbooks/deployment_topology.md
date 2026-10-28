# 部署拓扑（P0-02）

开发可以单进程用 SQLite。生产必须多进程可读同一份数据，所以生产真源是 PostgreSQL。

## 两种模式

| 模式 | 何时用 | 数据真源 | 进程 |
|------|--------|----------|------|
| 开发 | 本机 Portal `:5003` | `data/apk_site.db`（SQLite，WAL，线程内连接） | 一个 Waitress 进程 |
| 生产 | `APP_ENV=production` | `DATABASE_URL` 指向 PostgreSQL | 可以多个 worker |

生产启动时 [`require_production_secrets()`](../../portals/common/core/config.py) 缺密钥会退出，[`require_production_database()`](../../portals/common/core/config.py) 在 `DATABASE_URL` 不是 `postgres://` 或 `postgresql://` 时也会退出。SQLite 不能当生产真源。

## 不要这样做

- 不要用多个 worker 同时写 `data/apk_site.db`。SQLite 的线程连接不能代替进程间的单一真源。
- 不要把 `data/projects.json` 当主库。它只在 `SAVE_JSON_MIRROR=true` 时做镜像。
- 不要把 `build_nodes.json` 当节点名单。节点真源是 `infra_nodes` 表。

## 备份

见 [production_backup_restore.md](./production_backup_restore.md) 和 [postgres_migration.md](./postgres_migration.md)。

## 入口

人用的页面见 [entrypoint_map.md](../architecture/entrypoint_map.md)。渠道 Journey 的旧 URL 会跳转，不是主路径。
