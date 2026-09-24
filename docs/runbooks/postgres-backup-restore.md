# PostgreSQL backup and restore runbook

This runbook covers local Docker Compose backups and a repeatable restore drill. It does not replace managed, encrypted, off-site production backups.

## Safety and scope

- The commands target only the Compose `postgres` service in this repository.
- A restore drill creates a uniquely named `tap_restore_smoke_<random-id>` database, verifies its Alembic revision, and drops only that generated database. It does not drop, recreate, or modify the configured development database or its Docker volume.
- The smoke script refuses to run when `APP_ENV` is not `local` or `test`.
- Do not commit backup artifacts. They contain candidate and employee data. The repository ignores the `backups/` directory.
- Never use `docker compose down -v` as a backup or restore procedure; it deletes named volumes.

## Prerequisites

1. Start Docker Desktop.
2. From the repository root, ensure `.env` is configured and start PostgreSQL:

   ```bash
   docker compose up -d postgres
   docker compose ps postgres
   ```

3. Check that `APP_ENV=local` (or `APP_ENV=test`) is set in `.env` or the process environment.

## Create a local backup

From the repository root:

```bash
uv run --directory apps/api python ../../scripts/postgres_backup.py backup
```

The script writes a timestamped custom-format archive under `backups/`, refuses to overwrite an existing file, and streams binary data without PowerShell text encoding. To choose a path:

```bash
uv run --directory apps/api python ../../scripts/postgres_backup.py backup --output ../../backups/manual.dump
```

Keep backups in a protected location outside source control. A local dump on the same computer is not disaster recovery.

## Verify a backup by restoring it

Run:

```bash
uv run --directory apps/api python ../../scripts/postgres_backup.py restore-smoke
```

The smoke test creates a fresh custom-format backup, restores it into a random scratch database on the local PostgreSQL container, and verifies that the restored `alembic_version` matches the source. The scratch database and temporary dump are removed even if the restore or verification fails. A Docker/database outage fails the command; it does not fall back to the development database as a restore target.

For a saved archive from an earlier run, list its contents before restoring it:

```bash
docker compose exec -T postgres pg_restore --list < backups/your-backup.dump
```

To restore manually, provision a separate empty PostgreSQL instance/database first, then restore there (not over your active development database):

```bash
docker compose exec -T postgres createdb -U tap tap_restore_manual
docker compose exec -T postgres pg_restore --exit-on-error --no-owner --no-acl --dbname=tap_restore_manual < backups/your-backup.dump
```

Replace `tap` if your configured PostgreSQL role differs. Confirm the Alembic revision and application health before directing any clients to a restored environment. Remove only the explicitly created manual restore database when you are sure it is disposable:

```bash
docker compose exec -T postgres dropdb -U tap tap_restore_manual
```

## Production requirements

Production recovery must use the selected hosting provider's supported automated backup and point-in-time recovery capabilities. Configure encryption at rest and in transit, least-privilege access, retention and deletion policies, and a copy in a separate failure domain/account. Define and approve recovery point/time objectives (RPO/RTO), alert on missed backups, and perform periodic restore drills into an isolated environment. A database dump does not include application secrets, object-storage documents, or external integration state; those require separate backup and recovery plans. Do not store database passwords in shell history or backup command arguments.
