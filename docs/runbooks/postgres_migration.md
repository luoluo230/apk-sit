# PostgreSQL migration runbook (P0-02 Step 6 skeleton)

## Scope

This runbook covers moving from SQLite (`data/apk_site.db`) to PostgreSQL when `DATABASE_URL` is set.

**Current status:** Portal still uses SQLite as the production store. `DATABASE_URL` is reserved; factory wiring is planned in a follow-up PR.

## Prerequisites

- Backup SQLite: `cp data/apk_site.db data/apk_site.db.bak.$(date +%Y%m%d)`
- `SAVE_JSON_MIRROR=true` during transition (JSON mirrors under `data/`)

## Local Postgres

```bash
docker compose -f docker-compose.postgres.yml up -d
export DATABASE_URL=postgresql://apk_site:apk_site_dev@127.0.0.1:5432/apk_site
```

## Migration outline (not yet automated in portal)

1. Export typed registry tables: `projects`, `channels`, `project_versions`
2. Export release domain: `release_*`, `topology_bindings`
3. Export ops tables: `ops_*`
4. Import into Postgres with matching schema
5. Point portal at `DATABASE_URL`, set `USE_SQLITE=false`
6. Run pytest against Postgres-backed instance

Planned script: `portals/common/core/scripts/migrate_sqlite_to_postgres.py`

## Rollback

- Stop portal, restore `apk_site.db` backup
- Unset `DATABASE_URL`, set `USE_SQLITE=true`
- Restart single Waitress worker

## Verification

```bash
cd portals/common/core
python -m pytest tests/test_project_registry.py tests/test_project_repo_concurrency.py -q
```
