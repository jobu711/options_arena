# CLAUDE.md -- Data Layer (`data/`)

## Purpose

Async SQLite persistence for scan results, ticker scores, debates, analytics, metadata,
spreads, recommendations, and migration management. The **only** module that touches SQLite
for business data. `services/cache.py` has its own SQLite connection for ephemeral cache
data -- these are separate concerns.

Every public method returns typed Pydantic models from `models/`. No raw dicts, no
tuples, no `sqlite3.Row` objects cross the package boundary.

Use Glob to discover files.

---

## Mixin Decomposition

`Repository` is composed from six domain-specific mixins via multiple inheritance:

```
Repository(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin, SpreadsMixin, RecommendationMixin)
    all inherit from RepositoryBase (provides _db + commit())
```

| Mixin | Domain | Key Methods |
|-------|--------|-------------|
| `ScanMixin` | Scan runs + scores | `save_scan_run`, `save_ticker_scores`, `get_latest_scan`, `get_scan_by_id`, `get_scores_for_scan`, `get_recent_scans`, `get_score_history`, `get_trending_tickers` |
| `DebateMixin` | Debates + agents + agency | `save_debate`, `save_agent_predictions`, `get_debate_by_id`, `get_recent_debates`, `get_agent_accuracy`, `get_agent_calibration`, agency query persistence |
| `AnalyticsMixin` | Contracts + outcomes + backtesting | `save_recommended_contracts`, `save_contract_outcomes`, `get_win_rate_by_direction`, `get_equity_curve`, `get_drawdown_series`, `get_performance_summary`, + 10 more |
| `MetadataMixin` | Ticker classification cache | `upsert_ticker_metadata`, `upsert_ticker_metadata_batch`, `get_all_ticker_metadata`, `get_stale_tickers`, `get_metadata_coverage` |
| `SpreadsMixin` | Spread recommendations | `save_spread_recommendation`, `get_spread_for_ticker` |
| `RecommendationMixin` | Unified recommendations | `save_recommendation_result`, `get_recommendation_by_id`, `get_recent_recommendations` |

All mixins: parameterized queries, `aiosqlite.Row` for named access, optional `commit=False`
for batched atomic persistence, typed model returns.

`DebateRow` is a `@dataclass` defined in `_debate.py` (re-exported from `repository.py`
and `__init__.py`). It holds raw JSON strings from `ai_theses` -- not Pydantic because
fields contain unparsed JSON that callers deserialize on demand.

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Typed boundary** | Every public method returns a Pydantic model or primitive (`int` for lastrowid, `None` for not-found). Never `dict`, `tuple`, `Row`. |
| **Async-only** | All public methods are `async`. aiosqlite is inherently async. |
| **DI constructor** | `Database(db_path)`, `Repository(db)`. No global state, no singletons. |
| **Explicit lifecycle** | `await db.connect()` before use, `await db.close()` when done. Close is idempotent. |
| **Logging only** | `logging` module -- never `print()`. Migrations INFO, queries DEBUG. |
| **No business logic** | Persists and retrieves. Does not score, filter, price, or analyze. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (ScanRun, TickerScore, IndicatorSignals, ContractOutcome, etc.) | `services/` |
| `analysis/performance` (for risk-adjusted metrics) | `pricing/`, `scoring/` |
| `utils/exceptions.py` | `indicators/`, `agents/` |
| stdlib: `asyncio`, `logging`, `pathlib`, `json`, `datetime`, `decimal`, `dataclasses` | `cli/`, `reporting/` |
| External: `aiosqlite`, `numpy` | `scan/` |

---

## aiosqlite Patterns

### Connection Lifecycle

```python
db = await aiosqlite.connect(db_path)
await db.execute("PRAGMA journal_mode=WAL")
await db.execute("PRAGMA foreign_keys=ON")  # SQLite defaults to OFF!
# ... use db ...
await db.close()
```

- Pass `":memory:"` (string) for tests. `Path` for file-backed (production).
- Set `db.row_factory = aiosqlite.Row` for named column access (`row["column_name"]`).

### Critical Rules

1. **`await db.commit()` after EVERY write** -- aiosqlite does NOT auto-commit. Without it,
   changes are silently lost on connection close.
2. **Cursor as context manager** -- `async with db.execute(...) as cursor:` for queries.
3. **`executescript()` auto-commits** before execution (sqlite3 behavior). Each migration
   file is atomic at the file level.
4. **`lastrowid`** available on cursor after INSERT + commit.
5. **`executemany`** for batch inserts, followed by commit.
6. **`PRAGMA foreign_keys=ON`** required on every connection. SQLite defaults to OFF,
   silently ignoring `REFERENCES` constraints.

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

### Migration File Convention

- Location: `data/migrations/` (project root, NOT inside `src/`)
- Naming: `{NNN}_{description}.sql` -- e.g., `001_initial.sql` (37 files through `037_recommendation_results.sql`)
- Sorted by numeric prefix: `sorted(paths, key=lambda p: int(p.stem.split("_")[0]))`
- All tables use `CREATE TABLE IF NOT EXISTS` for safety

### Execution Flow

1. Open aiosqlite connection
2. Set `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`
3. Create `schema_version` table
4. Read migration files sorted by prefix
5. For each: check version in `schema_version`, skip if applied, `executescript()` if not
6. INSERT into `schema_version`, commit

### migrations_dir Resolution

`Database` accepts optional `migrations_dir: Path | None`:
- If provided, use directly
- If `None`, navigate from `database.py` to project root -> `data/migrations/`
- Tests: pass `migrations_dir=None` with `:memory:` -- real migrations still run

---

## Serialization Rules

### IndicatorSignals <-> JSON TEXT

```python
# Write: signals_json = score.signals.model_dump_json()
# Read:  signals = IndicatorSignals.model_validate_json(row["signals_json"])
```

- `model_dump_json()` handles `None` -> JSON `null`
- `model_validate_json()` handles `null` -> `None`
- Forward-compatible: new fields added to `IndicatorSignals` deserialize as `None` from old JSON

### StrEnum <-> TEXT

Use the enum constructor for deserialization: `ScanPreset(row["preset"])`. NOT `getattr()` --
constructor raises `ValueError` on unknown values (fail-fast).

### datetime <-> ISO 8601 TEXT

Store via `.isoformat()` (always UTC). Read via `datetime.fromisoformat()` (Python 3.11+
handles `+00:00`). The `ScanRun` validator requires UTC -- guaranteed because we store
`.isoformat()` output from UTC datetimes.

### Decimal

Store as TEXT via `str()`. Reconstruct via `Decimal(row["column"])`.

---

## Error Handling

- **No new exception class** -- use stdlib `sqlite3.IntegrityError` for constraint violations.
- **Connection state**: raise `RuntimeError` if operations on closed Database.
- **Never bare `except:`** -- always specific types.
- **Logging**: `logger = logging.getLogger(__name__)` in each file.
  - Migrations: INFO (`"Applied migration %s"`)
  - Queries: DEBUG (`"Saved scan run id=%d"`)
  - Errors: WARNING or ERROR with exception info

---

## Testing Guidance

- **In-memory DB** for all tests: `Database(":memory:")`. Fresh per test, no cleanup.
- Migrations run on each fresh DB. `pytest-asyncio` for all async tests.
- Assert: round-trip fidelity, enum reconstruction, UTC preservation, ordering, isolation.

---

## What Claude Gets Wrong Here (Fix These)

1. **Forgetting `await db.commit()`** -- aiosqlite does NOT auto-commit. Data silently lost.

2. **Positional row indexing** -- `row[0]`, `row[3]` is fragile. Use `row["column_name"]`
   with `db.row_factory = aiosqlite.Row`.

3. **Returning raw tuples** -- Reconstruct Pydantic models from every query. Never `list[tuple]`.

4. **String formatting in SQL** -- `f"SELECT * FROM x WHERE id = {id}"` is SQL injection.
   Always parameterized: `"... WHERE id = ?"`, `(id,)`.

5. **Forgetting `None` for optional fields** -- `completed_at` can be None. Store as NULL.

6. **`json.dumps` for IndicatorSignals** -- Use `model_dump_json()` / `model_validate_json()`.

7. **`schema_version` in migration file** -- Created by `Database.connect()` BEFORE migrations.

8. **`executescript()` side effect** -- Issues implicit COMMIT before execution.

9. **Missing `PRAGMA foreign_keys=ON`** -- SQLite defaults to OFF. Constraints silently ignored.

10. **Datetimes as epoch integers** -- Use ISO 8601 TEXT. `fromisoformat()` round-trips cleanly.

11. **ScanRun.id `None` on input** -- `id: int | None = None`. DB assigns. Return `int` ID.

12. **ScanRun is frozen** -- Cannot `scan_run.id = lastrowid`. Return ID separately.

13. **`typing.Optional[X]`** -- Use `X | None`. Python 3.13+.

14. **Bare `except:`** -- Always catch specific exception types.

15. **`print()` in data layer** -- Use `logging`. `logger = logging.getLogger(__name__)`.
