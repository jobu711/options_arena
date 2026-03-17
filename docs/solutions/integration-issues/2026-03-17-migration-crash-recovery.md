---
title: "SQLite executescript() crash window leaves migrations partially applied"
date: 2026-03-17
module: options_arena.data
problem_type: integration_issues
severity: high
symptoms:
  - "OperationalError: duplicate column name on restart after crash"
  - "Migration re-application fails after process kill during migration run"
  - "Non-idempotent DDL (ALTER TABLE ADD COLUMN) crashes on second application"
tags:
  - sqlite
  - migrations
  - executescript
  - crash-recovery
  - idempotent
root_cause: "executescript() issues implicit COMMIT before running DDL, but schema_version INSERT happens after — crash between them leaves migration applied but unrecorded"
---

## Problem

After a process crash during database migration, restarting the application failed with
`OperationalError: duplicate column name` or similar DDL errors. The migration had been
partially applied (DDL executed and auto-committed by `executescript()`) but not recorded
in `schema_version` (the INSERT + COMMIT that follows).

On restart, the migration runner saw the version was missing from `schema_version` and
tried to re-apply it, but the DDL had already executed (e.g., `ALTER TABLE ADD COLUMN`
already added the column).

Affected migrations: 002, 014, 020, 026, 030, 032 — any migration with non-idempotent DDL.

## Root Cause

`aiosqlite`'s `executescript()` inherits `sqlite3`'s behavior of issuing an implicit
`COMMIT` before executing the script content. This means:

1. `executescript(migration_sql)` — DDL runs and is auto-committed
2. `INSERT INTO schema_version(version, applied_at)` — records the migration
3. `commit()` — commits the schema_version record

If the process crashes between step 1 and step 3, the DDL is committed but the
schema_version record is not. On restart, the migration runner doesn't find the version
in schema_version, attempts to re-apply, and crashes on non-idempotent DDL.

## Solution

Added error handling in the migration runner (`database.py`) to catch `OperationalError`
from partially-applied migrations:

```python
import sqlite3

try:
    await conn.executescript(sql_content)
except sqlite3.OperationalError as exc:
    err_msg = str(exc).lower()
    if "duplicate column" in err_msg or "already exists" in err_msg:
        logger.warning(
            "Migration %03d appears partially applied (%s) — recording as applied",
            version, exc,
        )
    else:
        raise
```

When a DDL error indicates the migration was already partially applied (duplicate column,
table already exists), the runner logs a warning and records the migration as applied
rather than crashing.

**Important**: Catch `sqlite3.OperationalError`, NOT generic `Exception`. Catching
`Exception` would suppress unrelated errors like `MemoryError` or `IOError` and mark a
migration as applied when it wasn't. DDL failures always raise `OperationalError`.

## Prevention Rule

1. **New migrations should be idempotent** — use `CREATE TABLE IF NOT EXISTS`,
   `CREATE INDEX IF NOT EXISTS`. SQLite lacks `ADD COLUMN IF NOT EXISTS`, but the
   migration runner now handles the crash recovery case.
2. **Never assume executescript() is atomic** — it auto-commits before running.
3. **Test crash recovery** — verify that killing the process mid-migration and
   restarting produces a working database.

## Related

- P1-6 in `.claude/audits/FULL_AUDIT.md`
- `src/options_arena/data/database.py` — migration runner
- `data/migrations/` — 33 sequential migration files
