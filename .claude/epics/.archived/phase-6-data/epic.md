---
name: phase-6-data
status: completed
created: 2026-02-22T08:50:13Z
updated: 2026-02-23T18:50:16Z
completed: 2026-02-23T18:50:16Z
progress: 100%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/39
---

# Epic 6: Data Layer

## Overview

Build the `data/` package from scratch: an async SQLite persistence layer for scan
results, ticker scores, and service cache. Three source files (`database.py`,
`repository.py`, `__init__.py`), one SQL migration, and comprehensive tests.

**Full rewrite** — no cherry-picking from v3. All code written fresh against the
current model layer and aiosqlite API (Context7-verified).

## Scope

### PRD Requirements Covered
FR-D1, FR-D2, FR-D3

### Pre-requisite: `data/CLAUDE.md`

Before writing ANY code in the `data/` package, the module-level `CLAUDE.md` must be
written and committed. This file defines the architecture rules, aiosqlite patterns,
serialization conventions, and common mistakes for the data layer. All subsequent
implementation issues depend on it.

### Deliverables

**`src/options_arena/data/CLAUDE.md`** — Module conventions (written first):
- Purpose and file listing
- aiosqlite patterns (Context7-verified): connect, WAL, execute, commit, row_factory
- Serialization rules: `IndicatorSignals` ↔ JSON, `ScanPreset`/`SignalDirection` ↔ string, `datetime` ↔ ISO 8601 string
- Migration runner design: sequential numbered files, `schema_version` table, idempotent
- Repository method signatures and return types
- Error handling: `DatabaseError` exception, never bare `except:`
- Test patterns: in-memory `:memory:` SQLite, no file I/O, `pytest-asyncio`
- Common mistakes to avoid

---

**`src/options_arena/data/database.py`** — Async SQLite lifecycle:
- `Database` class with DI constructor: `__init__(self, db_path: Path | str)` — accepts
  `":memory:"` for tests, filesystem `Path` for production
- `async def connect()` — open `aiosqlite` connection, enable WAL mode (`PRAGMA journal_mode=WAL`),
  enable foreign keys (`PRAGMA foreign_keys=ON`), run pending migrations
- `async def close()` — close connection safely (idempotent, safe to call multiple times)
- `async def connection` property or getter — returns the live `aiosqlite.Connection`
  (raises if not connected)
- Migration runner:
  - Reads `data/migrations/*.sql` files sorted by numeric prefix (001, 002, ...)
  - Tracks applied migrations in `schema_version(version INTEGER PRIMARY KEY, applied_at TEXT)`
  - Skips already-applied migrations (idempotent re-run)
  - Executes each migration inside a transaction (`BEGIN`/`COMMIT`)
  - Uses `executescript()` for multi-statement SQL files
- No business logic — pure infrastructure

**`src/options_arena/data/repository.py`** — Typed CRUD operations:
- `Repository` class with DI constructor: `__init__(self, db: Database)`
- Write operations:
  - `async def save_scan_run(scan_run: ScanRun) -> int` — INSERT, return `lastrowid`
  - `async def save_ticker_scores(scan_id: int, scores: list[TickerScore]) -> None` — batch INSERT via `executemany`
- Read operations:
  - `async def get_latest_scan() -> ScanRun | None` — ORDER BY id DESC LIMIT 1
  - `async def get_scan_by_id(scan_id: int) -> ScanRun | None`
  - `async def get_scores_for_scan(scan_id: int) -> list[TickerScore]` — with `IndicatorSignals` deserialization
  - `async def get_recent_scans(limit: int = 10) -> list[ScanRun]`
- All queries return typed Pydantic models, never raw dicts or tuples
- `IndicatorSignals` serialized to/from JSON via `model_dump_json()` / `IndicatorSignals.model_validate_json()`
- `ScanPreset` and `SignalDirection` stored as their string values, reconstructed via enum constructor
- `datetime` fields stored as ISO 8601 strings, parsed back with `datetime.fromisoformat()`

**`src/options_arena/data/__init__.py`** — Re-export `Database`, `Repository`

---

**`data/migrations/001_initial.sql`** — Initial schema:

```sql
-- schema_version: migration tracking (managed by Database, not user SQL)
-- Already created by Database.connect() before migrations run

-- scan_runs: metadata for completed scan runs
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,          -- ISO 8601 UTC
    completed_at TEXT,                 -- ISO 8601 UTC, NULL if incomplete
    preset TEXT NOT NULL,              -- ScanPreset enum value
    tickers_scanned INTEGER NOT NULL,
    tickers_scored INTEGER NOT NULL,
    recommendations INTEGER NOT NULL
);

-- ticker_scores: scored tickers linked to a scan run
CREATE TABLE IF NOT EXISTS ticker_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    composite_score REAL NOT NULL,
    direction TEXT NOT NULL,           -- SignalDirection enum value
    signals_json TEXT NOT NULL,        -- IndicatorSignals.model_dump_json()
    UNIQUE(scan_run_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_ticker_scores_scan_id ON ticker_scores(scan_run_id);

-- service_cache: key-value cache with TTL (used by ServiceCache)
-- NOTE: ServiceCache already creates this table itself in cache.py.
-- This migration ensures it exists for fresh databases that skip cache init.
CREATE TABLE IF NOT EXISTS service_cache (
    key TEXT PRIMARY KEY,
    value BLOB,
    expires_at REAL
);

-- v2 placeholders (tables created now, unused in MVP)

-- ai_theses: AI debate results (v2)
CREATE TABLE IF NOT EXISTS ai_theses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    bull_json TEXT,
    bear_json TEXT,
    risk_json TEXT,
    verdict_json TEXT,
    created_at TEXT NOT NULL           -- ISO 8601 UTC
);

-- watchlists: user-defined watchlists (v2)
CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL           -- ISO 8601 UTC
);

-- watchlist_tickers: tickers in a watchlist (v2)
CREATE TABLE IF NOT EXISTS watchlist_tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id),
    ticker TEXT NOT NULL,
    added_at TEXT NOT NULL,            -- ISO 8601 UTC
    UNIQUE(watchlist_id, ticker)
);
```

---

**Tests (`tests/unit/data/`)** — ~35 tests:

`test_database.py`:
- WAL mode enabled after connect (`PRAGMA journal_mode` returns `wal`)
- Foreign keys enabled after connect (`PRAGMA foreign_keys` returns `1`)
- Migration creates all expected tables (scan_runs, ticker_scores, service_cache, ai_theses, watchlists, watchlist_tickers)
- `schema_version` table tracks applied migrations
- Idempotent re-run: calling `connect()` twice doesn't fail or re-apply migrations
- Close is idempotent (calling close twice doesn't raise)
- Operations after close raise an error
- `:memory:` database works (no file I/O)

`test_repository.py`:
- `save_scan_run` returns integer ID > 0
- `get_latest_scan` returns `None` on empty database
- `get_latest_scan` returns the most recently inserted `ScanRun`
- `save_scan_run` → `get_scan_by_id` round-trip preserves all fields
- `ScanPreset` enum round-trip: stored as string, reconstructed as enum
- `SignalDirection` enum round-trip: stored as string, reconstructed as enum
- `datetime` round-trip: UTC preserved through ISO 8601 serialization
- `save_ticker_scores` persists batch, `get_scores_for_scan` retrieves all
- `IndicatorSignals` JSON round-trip: all-None, partial-fill, full-fill
- `TickerScore.scan_run_id` set correctly on retrieval
- `get_scores_for_scan` returns empty list for nonexistent scan_id
- `get_recent_scans` respects limit parameter
- `get_recent_scans` returns scans in descending order (newest first)
- Unique constraint: duplicate (scan_run_id, ticker) raises error
- Multiple scan runs with different scores: correct isolation

`test_migration.py`:
- Fresh `:memory:` database has all tables after connect
- Each table has expected columns (verified via `PRAGMA table_info`)
- Indexes exist (verified via `PRAGMA index_list`)
- Foreign keys are present (verified via `PRAGMA foreign_key_list`)

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

All three must pass. Existing 871 tests must not regress.

## Dependencies
- **Blocked by**: Phase 1 (models — `ScanRun`, `TickerScore`, `IndicatorSignals`, `ScanPreset`, `SignalDirection`) — **already complete**
- **Blocks**: Phase 7 (scan pipeline — needs persistence for scan results)
- **No dependency on**: `services/cache.py` — the `service_cache` table is duplicated
  intentionally (ServiceCache creates it on init; migration ensures it exists for fresh DBs)

## Key Design Decisions

1. **Full rewrite, no cherry-pick** — All code written from scratch against current
   models and Context7-verified aiosqlite API. No v3 code carried forward.

2. **`IndicatorSignals` as JSON column** — 18 named fields serialized via Pydantic's
   `model_dump_json()` → TEXT column. Deserialized via `IndicatorSignals.model_validate_json()`.
   This preserves `None` values (indicator not computed) and is forward-compatible with
   new indicator fields.

3. **Enums stored as string values** — `ScanPreset.FULL` → `"full"` in SQLite. Reconstructed
   via `ScanPreset(row["preset"])`. StrEnum makes this natural.

4. **Datetimes as ISO 8601 TEXT** — SQLite has no native datetime type. Store as
   `"2026-02-23T17:55:14+00:00"` TEXT, parse via `datetime.fromisoformat()`. Always UTC.

5. **`schema_version` table created by Database, not in migrations** — The migration runner
   needs this table to exist before it reads migration files. Database.connect() creates it
   first, then runs numbered migrations.

6. **In-memory SQLite for all tests** — `Database(":memory:")` — no temp files, no cleanup,
   fast. Each test gets a fresh database.

7. **v2 tables created now, unused in MVP** — `ai_theses`, `watchlists`, `watchlist_tickers`
   are in the initial migration to avoid a future migration when v2 features land.

8. **`service_cache` table in migration AND in ServiceCache** — Both create it with
   `CREATE TABLE IF NOT EXISTS`. ServiceCache.init_db() handles its own table creation
   for standalone use (e.g., when Database hasn't been initialized). The migration ensures
   the table exists in fresh databases before ServiceCache connects.

9. **Migration files live at project root** — `data/migrations/*.sql`, not inside `src/`.
   The `Database` class accepts a `migrations_dir` parameter (defaulting to
   `Path(__file__).resolve().parents[3] / "data" / "migrations"` for the standard layout).

10. **`executescript()` for migrations** — aiosqlite's `executescript()` runs multiple
    SQL statements in a single call. Each migration file can contain multiple CREATE TABLE
    statements.

## Tasks Created
- [ ] #40 - Write data/CLAUDE.md module conventions (parallel: false)
- [ ] #41 - Write 001_initial.sql migration (parallel: false, depends: #40)
- [ ] #42 - Implement database.py — Database class with migration runner (parallel: false, depends: #40, #41)
- [ ] #43 - Implement repository.py — typed CRUD for ScanRun and TickerScore (parallel: false, depends: #40, #42)
- [ ] #44 - Package init, migration tests, and full pipeline verification (parallel: false, depends: #42, #43)

Total tasks: 5
Parallel tasks: 0
Sequential tasks: 5 (strict dependency chain)
Estimated total effort: 10.5 hours

## Estimated Tests: ~35
