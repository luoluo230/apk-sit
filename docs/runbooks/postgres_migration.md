# PostgreSQL migration runbook

This runbook moves the Portal/BaaS control plane from SQLite (`data/apk_site.db`) to PostgreSQL. PostgreSQL is the production source of truth; SQLite and JSON mirrors are migration inputs only.

## Preconditions

1. Put the Portal in maintenance mode and stop every worker.
2. Set `DATABASE_URL` to the target PostgreSQL database. Use a least-privilege migration account that can create the application schema and write its rows.
3. Take and retain an off-host backup. The backup must include the PostgreSQL custom dump, SQLite source, and checksum manifest:

```powershell
powershell -File scripts/Backup-PortalData.ps1 -DatabaseUrl $env:DATABASE_URL -RequirePostgres -OutputDir D:\backups\apk-site
```

4. Record the backup archive path and SHA-256 in the release ticket. Do not put a database URL or password in the ticket.

## Plan and migrate

Generate a non-writing inventory first. Preserve the JSON report with the change record:

```powershell
py -3 portals/common/core/scripts/migrate_sqlite_to_postgres.py --dry-run --report D:\migration-evidence\sqlite-inventory.json
```

Apply only after the inventory, backup, and maintenance window are approved:

```powershell
py -3 portals/common/core/scripts/migrate_sqlite_to_postgres.py --apply --database-url $env:DATABASE_URL --report D:\migration-evidence\postgres-migration.json
```

The tool initializes the current PostgreSQL schema first, migrates only source columns that exist in that schema, uses conflict-safe inserts, and lists skipped legacy tables in the report. It does not expose database credentials in the report. Large operational tables should be archived before cutover; `request_events` is telemetry and is not a reason to delay the authoritative release/config tables.

## Verify and switch traffic

```powershell
$env:DATABASE_URL = '<managed PostgreSQL connection string>'
py -3 portals/common/core/scripts/db_readiness_check.py --require-postgres
cd portals/common/core
py -3 -m pytest tests/test_project_registry.py tests/test_project_repo_concurrency.py -q
```

Start a single Portal worker against PostgreSQL, verify `/health`, then run the client/server release-contract gate before gradually reopening traffic. Scale workers only after that deployment passes.

## Rollback

Stop Portal workers before restoration. Verify the backup before any write, then restore it explicitly:

```powershell
powershell -File scripts/Restore-PortalData.ps1 -BackupPath D:\backups\apk-site\apk-site-backup-*.zip
powershell -File scripts/Restore-PortalData.ps1 -BackupPath D:\backups\apk-site\apk-site-backup-*.zip -DatabaseUrl $env:DATABASE_URL -ConfirmRestore
```

The first command only verifies manifest hashes. The second restores the SQLite source and, when present, the PostgreSQL custom dump. Re-run the readiness and smoke checks before reopening traffic.
