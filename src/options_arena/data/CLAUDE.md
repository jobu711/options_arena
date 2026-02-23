# CLAUDE.md — Data Layer (`data/`)

## Purpose

Async SQLite persistence for scan results, ticker scores, and migration management.
The **only** module that touches SQLite for business data. `services/cache.py` has its
own SQLite connection for ephemeral cache data — these are separate concerns.

Every public method returns typed Pydantic models from `models/`. No raw dicts, no
tuples, no `sqlite3.Row` objects cross the package boundary.

## Files

| File | Class / Purpose | Public? |
|------|----------------|---------|
| `database.py` | `Database` — async SQLite lifecycle, WAL mode, migration runner | Yes |
| `repository.py` | `Repository` — typed CRUD for `ScanRun` and `TickerScore` | Yes |
| `__init__.py` | Re-exports `Database`, `Repository` with `__all__` | Yes |

External:
| File | Purpose |
|------|---------|
| `data/migrations/001_initial.sql` | Initial schema (project root, not in `src/`) |

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Typed boundary** | Every public method returns a Pydantic model (`ScanRun`, `TickerScore`, `list[...]`) or a primitive (`int` for lastrowid, `None` for not-found). Never `dict`, `tuple`, `Row`. |
| **Async-only** | All public methods are `async`. aiosqlite is inherently async. |
| **DI constructor** | `Database(db_path)`, `Repository(db)`. No global state, no singletons. |
| **Explicit lifecycle** | `await db.connect()` before use, `await db.close()` when done. Close is idempotent. |
| **Logging only** | `logging` module — never `print()`. Log migrations at INFO, queries at DEBUG. |
| **No business logic** | This module persists and retrieves. It does not score, filter, price, or analyze. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (ScanRun, TickerScore, IndicatorSignals, ScanPreset, SignalDirection) | `services/` |
| `utils/exceptions.py` (for custom exception, if needed) | `pricing/`, `scoring/` |
| stdlib: `asyncio`, `logging`, `pathlib`, `json`, `datetime` | `indicators/`, `agents/` |
| External: `aiosqlite` | `cli.py`, `reporting/` |

---

## aiosqlite Patterns (Context7-Verified)

### Connection Lifecycle

```python
import aiosqlite

# Open connection — returns Connection object
db = await aiosqlite.connect(db_path)

# Configure for performance
await db.execute("PRAGMA journal_mode=WAL")
await db.execute("PRAGMA foreign_keys=ON")

# ... use db ...

# Close when done
await db.close()
```

**Critical**: `aiosqlite.connect()` accepts `str` or `Path`. Pass `":memory:"` (string)
for in-memory databases (tests). Pass a `Path` for file-backed databases (production).

### Execute + Commit

```python
# Writes MUST be followed by commit — aiosqlite does NOT auto-commit
await db.execute(
    "INSERT INTO scan_runs (started_at, preset, ...) VALUES (?, ?, ...)",
    (started_at_iso, preset_str, ...),
)
await db.commit()
```

**Critical**: Every write (`INSERT`, `UPDATE`, `DELETE`) needs `await db.commit()`.
Without it, changes are lost when the connection closes.

### Query with Cursor

```python
# Context-managed cursor — recommended pattern
async with db.execute(
    "SELECT * FROM scan_runs WHERE id = ?", (scan_id,)
) as cursor:
    row = await cursor.fetchone()
    # row is tuple | None

# For multiple rows:
async with db.execute(
    "SELECT * FROM ticker_scores WHERE scan_run_id = ?", (scan_id,)
) as cursor:
    rows = await cursor.fetchall()
    # rows is list[tuple]
```

### Row Factory for Named Access

```python
import aiosqlite

db.row_factory = aiosqlite.Row
async with db.execute("SELECT * FROM scan_runs") as cursor:
    async for row in cursor:
        value = row["preset"]  # dict-like access by column name
```

**Use `aiosqlite.Row`** on the `Database` connection after opening. This allows
`row["column_name"]` access in the Repository instead of fragile positional indexing.

### executescript for Migrations

```python
# executescript runs multiple SQL statements in one call
# NOTE: executescript issues an implicit COMMIT before execution
sql_content = migration_path.read_text(encoding="utf-8")
await db.executescript(sql_content)
```

**Critical**: `executescript()` auto-commits before running. This is sqlite3 behavior
inherited by aiosqlite. Each migration file is atomic at the file level.

### lastrowid

```python
cursor = await db.execute("INSERT INTO scan_runs (...) VALUES (...)", params)
await db.commit()
row_id = cursor.lastrowid  # int — the ID of the inserted row
```

### executemany for Batch Inserts

```python
await db.executemany(
    "INSERT INTO ticker_scores (scan_run_id, ticker, ...) VALUES (?, ?, ...)",
    [(scan_id, score.ticker, ...) for score in scores],
)
await db.commit()
```

---

## Migration Runner Design

### schema_version Table

Created by `Database.connect()` BEFORE reading any migration files:

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
```

This table tracks which numbered migrations have been applied.

### Migration File Convention

- Location: `data/migrations/` (project root, NOT inside `src/`)
- Naming: `{NNN}_{description}.sql` — e.g., `001_initial.sql`, `002_add_watchlist_notes.sql`
- Sorted by numeric prefix: `sorted(paths, key=lambda p: int(p.stem.split("_")[0]))`
- Each file contains one or more `CREATE TABLE` / `CREATE INDEX` statements
- All tables use `CREATE TABLE IF NOT EXISTS` for safety

### Migration Execution Flow

```
1. Database.connect() called
2. Open aiosqlite connection
3. Set PRAGMA journal_mode=WAL
4. Set PRAGMA foreign_keys=ON
5. CREATE TABLE IF NOT EXISTS schema_version(...)
6. Read migration files from migrations_dir, sorted by prefix number
7. For each migration:
   a. Check if version number exists in schema_version
   b. If already applied → skip
   c. If not applied → executescript(sql_content)
   d. INSERT INTO schema_version (version, applied_at) VALUES (?, ?)
   e. Commit
8. Connection is ready for use
```

### migrations_dir Resolution

The `Database` class accepts an optional `migrations_dir: Path | None` parameter:
- If provided, use it directly
- If `None`, default to `Path(__file__).resolve().parents[3] / "data" / "migrations"`
  (navigates from `src/options_arena/data/database.py` → project root → `data/migrations/`)
- For tests, pass `migrations_dir=None` with `:memory:` — migration files are still read
  from the project root (tests verify real migrations work)

---

## Serialization Rules

### IndicatorSignals ↔ JSON TEXT

```python
# Serialize (write)
signals_json = score.signals.model_dump_json()
# Produces: '{"rsi": 65.2, "adx": null, "bb_width": 42.1, ...}'

# Deserialize (read)
signals = IndicatorSignals.model_validate_json(row["signals_json"])
```

- `model_dump_json()` handles `None` → JSON `null` naturally
- `model_validate_json()` handles JSON `null` → Python `None` naturally
- 18 named fields round-trip perfectly — no data loss
- Forward-compatible: if new fields are added to `IndicatorSignals`, old JSON
  without those fields will deserialize with the new fields as `None` (default)

### StrEnum ↔ TEXT

```python
# Serialize (write) — StrEnum.value is already a string
preset_str = scan_run.preset.value  # "full", "sp500", "etfs"
# Or just: str(scan_run.preset) — StrEnum is a str subclass

# Deserialize (read) — enum constructor from string
preset = ScanPreset(row["preset"])  # ScanPreset("full") → ScanPreset.FULL
direction = SignalDirection(row["direction"])
```

**Critical**: Use the enum constructor, NOT `getattr`. `ScanPreset(row["preset"])` raises
`ValueError` on unknown values (fail-fast). `getattr` would silently return nonsense.

### datetime ↔ ISO 8601 TEXT

```python
# Serialize (write) — always UTC
started_at_str = scan_run.started_at.isoformat()
# Produces: "2026-02-23T17:55:14+00:00"

# Deserialize (read)
from datetime import datetime
started_at = datetime.fromisoformat(row["started_at"])
# Returns: datetime(2026, 2, 23, 17, 55, 14, tzinfo=timezone.utc)
```

**Critical**: `datetime.fromisoformat()` (Python 3.11+) handles `+00:00` suffix and
produces a timezone-aware datetime. The `ScanRun` validator requires UTC — this is
guaranteed because we always store `.isoformat()` output from UTC datetimes.

### Decimal — NOT stored directly

`ScanRun` and `TickerScore` don't have `Decimal` fields, so no Decimal serialization
is needed in this module. If future models add Decimal fields, store as TEXT via `str()`,
reconstruct via `Decimal(row["column"])`.

---

## Repository Method Signatures

```python
class Repository:
    def __init__(self, db: Database) -> None: ...

    async def save_scan_run(self, scan_run: ScanRun) -> int:
        """Persist a ScanRun. Returns the database-assigned ID (lastrowid)."""

    async def save_ticker_scores(self, scan_id: int, scores: list[TickerScore]) -> None:
        """Batch-insert TickerScores for a scan run. Sets scan_run_id on each."""

    async def get_latest_scan(self) -> ScanRun | None:
        """Get the most recent ScanRun, or None if no scans exist."""

    async def get_scan_by_id(self, scan_id: int) -> ScanRun | None:
        """Get a ScanRun by its ID, or None if not found."""

    async def get_scores_for_scan(self, scan_id: int) -> list[TickerScore]:
        """Get all TickerScores for a scan run. Returns empty list if none."""

    async def get_recent_scans(self, limit: int = 10) -> list[ScanRun]:
        """Get the N most recent ScanRuns, newest first."""
```

All methods:
- Accept and return Pydantic models (not dicts, not tuples)
- Use parameterized queries (`?` placeholders) — never f-strings or string formatting
- Call `await db.commit()` after every write
- Use `aiosqlite.Row` for named column access in queries

---

## Error Handling

- **No new exception class needed** — use stdlib `sqlite3.IntegrityError` (re-raised by
  aiosqlite) for constraint violations (duplicate scan_run_id + ticker). Let it propagate
  to the caller.
- **Connection state**: raise `RuntimeError` if operations attempted on a closed Database.
- **Never bare `except:`** — always catch specific types.
- **Logging**: `logger = logging.getLogger(__name__)` in each file.
  - Migrations: INFO (`"Applied migration %s"`)
  - Queries: DEBUG (`"Saved scan run id=%d"`, `"Retrieved %d scores for scan %d"`)
  - Errors: WARNING or ERROR with exception info

---

## Test Patterns

### In-Memory Database for All Tests

```python
import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()

@pytest_asyncio.fixture
async def repo(db: Database):
    return Repository(db)
```

- Every test gets a fresh `:memory:` database — no file I/O, no cleanup needed
- Migrations run on each fresh database (verifies migration correctness every time)
- `pytest-asyncio` with `@pytest.mark.asyncio` on all async tests

### Test Fixtures for Models

```python
from datetime import UTC, datetime
from options_arena.models import ScanRun, ScanPreset, TickerScore, SignalDirection, IndicatorSignals

def make_scan_run(**overrides):
    defaults = {
        "started_at": datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 15, 10, 35, 0, tzinfo=UTC),
        "preset": ScanPreset.SP500,
        "tickers_scanned": 500,
        "tickers_scored": 450,
        "recommendations": 8,
    }
    defaults.update(overrides)
    return ScanRun(**defaults)

def make_ticker_score(**overrides):
    defaults = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)
```

### What to Assert

- **Round-trip fidelity**: Write → Read → assert all fields match original model
- **Enum reconstruction**: `ScanPreset` and `SignalDirection` come back as enum members, not strings
- **datetime preservation**: UTC timezone survives round-trip
- **IndicatorSignals JSON**: `None` fields stay `None`, float fields preserve values
- **Ordering**: `get_recent_scans` returns newest first
- **Isolation**: Scores for scan A don't appear when querying scan B
- **Empty state**: `get_latest_scan()` returns `None` on empty DB, `get_scores_for_scan(999)` returns `[]`

---

## What Claude Gets Wrong Here (Fix These)

1. **Forgetting `await db.commit()` after writes** — aiosqlite does NOT auto-commit.
   Every INSERT/UPDATE/DELETE must be followed by `await db.commit()`. Without it,
   data is silently lost on connection close.

2. **Positional row indexing instead of named access** — `row[0]`, `row[3]` is fragile
   and breaks when columns are reordered. Set `db.row_factory = aiosqlite.Row` and use
   `row["column_name"]`.

3. **Returning raw tuples from queries** — The Repository MUST reconstruct Pydantic models
   from every query result. Never return `list[tuple]` or `dict`.

4. **String formatting in SQL** — `f"SELECT * FROM x WHERE id = {id}"` is SQL injection.
   Always use parameterized queries: `"SELECT * FROM x WHERE id = ?"`, `(id,)`.

5. **Forgetting to handle `None` for optional fields** — `completed_at` can be `None` on
   `ScanRun`. Store as SQL `NULL`, check for `None` when reconstructing.

6. **Using `json.dumps`/`json.loads` for IndicatorSignals** — Use Pydantic's
   `model_dump_json()` and `model_validate_json()` which handle all field types correctly
   (including `None` → `null`). Don't bypass Pydantic serialization.

7. **Creating `schema_version` inside the migration file** — The migration runner needs
   `schema_version` to exist BEFORE reading migration files. `Database.connect()` creates
   it, then runs migrations. Never put it in `001_initial.sql`.

8. **Using `executescript()` without understanding it auto-commits** — `executescript()`
   issues an implicit COMMIT before execution (sqlite3 behavior). This means any pending
   uncommitted changes are committed. Be aware of this side effect.

9. **Missing `PRAGMA foreign_keys=ON`** — SQLite has foreign keys OFF by default. Without
   this PRAGMA, `REFERENCES` constraints are ignored. Set it on every connection.

10. **Storing datetimes as epoch integers** — Use ISO 8601 TEXT. Epoch integers lose timezone
    info and are unreadable in manual queries. `datetime.fromisoformat()` round-trips cleanly.

11. **Not handling ScanRun.id being `None` on input** — `ScanRun` has `id: int | None = None`.
    When saving, `id` is `None` (DB assigns it). When reading, `id` is the DB value. The
    Repository must handle both states correctly.

12. **Forgetting `frozen=True` on ScanRun** — `ScanRun` is frozen. You cannot set
    `scan_run.id = lastrowid` after construction. The `save_scan_run` method returns the
    `int` ID; callers reconstruct the model if they need one with the ID set.

13. **Using `typing.Optional[X]`** — Use `X | None`. Python 3.13+ project.

14. **Bare `except:`** — Always catch specific exception types.

15. **`print()` in data layer code** — Use `logging` module. `logger = logging.getLogger(__name__)`.
