---
name: phase-6-data
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 6: Data Layer

## Overview

Build the `data/` package: cherry-pick the async SQLite database class and migration runner from v3, update the repository for new models (`IndicatorSignals` serialization), and write the initial schema migration.

## Scope

### PRD Requirements Covered
FR-D1, FR-D2, FR-D3

### Deliverables

**`src/options_arena/data/`:**

- `database.py` — Cherry-pick from v3:
  - Async SQLite via `aiosqlite`
  - WAL mode for concurrent reads
  - Sequential migration runner (reads `data/migrations/*.sql` in order)
  - Context-managed connections

- `repository.py` — Cherry-pick + update:
  - `save_scan_run(scan_run: ScanRun)` — persist scan metadata
  - `save_ticker_scores(scores: list[TickerScore])` — persist scores with `IndicatorSignals` serialization (JSON column)
  - `get_latest_scan() -> ScanRun | None`
  - `get_scores_for_scan(scan_id: int) -> list[TickerScore]`
  - All queries return typed Pydantic models, never raw dicts

- `__init__.py` — Re-export `Database`, `Repository`

**`data/migrations/`:**

- `001_initial.sql` — Schema:
  - `schema_version` — migration tracking
  - `scan_runs` — scan metadata (id, timestamp, preset, ticker_count, duration)
  - `ticker_scores` — scored tickers (scan_id FK, ticker, composite_score, direction, signals JSON)
  - `service_cache` — key-value cache with TTL (key, value JSON, expires_at)
  - `ai_theses` — placeholder for v2 (scan_id FK, ticker, bull/bear/risk JSON)
  - `watchlists`, `watchlist_tickers` — placeholder for v2

**Tests (`tests/unit/data/`):**
- Database: WAL mode verification, migration execution, connection lifecycle
- Repository: CRUD operations, `IndicatorSignals` JSON round-trip, query by scan_id
- Migration: schema creation, idempotent re-run
- ~30 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models — `ScanRun`, `TickerScore`, `IndicatorSignals`)
- **Blocks**: Epic 7 (scan pipeline — Phase 4 persistence)
- **Parallelizable**: Can run in parallel with Epics 2, 3, 5 after Epic 1 completes

## Key Decisions
- `IndicatorSignals` serialized as JSON column (18 named fields → JSON object)
- v2 tables (`ai_theses`, `watchlists`) created in initial migration but unused in MVP
- In-memory SQLite for tests (no file I/O in unit tests)

## Estimated Tests: ~30
