# Research: repository-decomposition

## PRD Summary

Split the monolithic `Repository` class (1,769 LOC, 47 methods, 8 domains) in
`src/options_arena/data/repository.py` into 4 domain-specific mixin classes plus a
`RepositoryBase`. The public `Repository` class becomes a thin MRO composition (~30 LOC).
Zero consumer changes across `api/`, `cli/`, `scan/`, `agents/`, and `services/`.

## Relevant Existing Modules

- `src/options_arena/data/repository.py` — The 1,769-line monolith being decomposed. Contains
  47 async methods across 7 comment-banner sections, 8 `_row_to_*` static helpers, and the
  `DebateRow` dataclass.
- `src/options_arena/data/database.py` — 115-line `Database` class providing `conn` property,
  `connect()`, `close()`, and WAL-mode migration runner. Unchanged by this refactor.
- `src/options_arena/data/__init__.py` — Re-exports `Database`, `DebateRow`, `Repository`.
  Must remain unchanged.
- `data/migrations/` — 28 sequential SQL migrations. Unchanged by this refactor.

## Existing Patterns to Reuse

- **DI constructor pattern**: `Repository(db: Database)` — single dependency, stored as `self._db`.
  The `RepositoryBase.__init__` will follow this exact pattern.
- **`conn = self._db.conn` accessor**: Every method accesses the database through `self._db.conn`.
  All mixins will use this same pattern, resolved via MRO through `RepositoryBase._db`.
- **`commit=False` atomic pattern**: 4 write methods accept `commit: bool = True`. The scan pipeline
  calls them with `commit=False` then calls `repo.commit()` once. `commit()` stays on `RepositoryBase`.
- **`_row_to_*` static helpers**: Each domain has `@staticmethod` row-to-model converters. These
  colocate naturally with the mixin that uses them.
- **Re-export pattern**: Package `__init__.py` re-exports public API. Consumers import from the
  package, not submodules. This pattern is preserved — mixin files are private (`_scan.py`).

## Existing Code to Extend

- **`repository.py` lines 95–115**: Class definition + `__init__` + `commit()` → becomes `RepositoryBase`
  in `_base.py` (~20 LOC)
- **`repository.py` lines 117–448**: Scan persistence (8 methods) + Debate persistence (6 methods) →
  `_scan.py` (~350 LOC) and `_debate.py` (~400 LOC)
- **`repository.py` lines 450–589**: Score history (3 methods) → `_scan.py` (same tables: `scan_runs`,
  `ticker_scores`)
- **`repository.py` lines 591–1379**: Analytics contracts, outcomes, queries (18 methods) →
  `_analytics.py` (~650 LOC)
- **`repository.py` lines 1381–1511**: Ticker metadata (7 methods) → `_metadata.py` (~200 LOC)
- **`repository.py` lines 1512–1769**: Agent calibration (4 methods) → `_debate.py` (same domain:
  `agent_predictions`, `auto_tune_weights`)

### Comment-Banner Sections (Current Groupings)

| Line Range | Banner | Target Mixin |
|-----------|--------|-------------|
| 117–276 | (implicit — scan/score) | `ScanMixin` |
| 278–448 | `# Debate persistence` | `DebateMixin` |
| 450–589 | `# Score history` | `ScanMixin` |
| 591–835 | `# Analytics: Contracts & Normalization` | `AnalyticsMixin` |
| 837–995 | `# Analytics: Outcomes` | `AnalyticsMixin` |
| 997–1379 | `# Analytics: Queries` | `AnalyticsMixin` |
| 1381–1511 | `# Ticker metadata persistence` | `MetadataMixin` |
| 1512–1769 | `# Agent calibration queries` | `DebateMixin` |

## Consumer Mapping

### Production Code Imports

| Consumer | Import Style | Methods Used | Mixin Domain(s) |
|----------|-------------|-------------|-----------------|
| `api/app.py` | `from options_arena.data import ...` | Constructor | — |
| `api/deps.py` | `from options_arena.data import ...` | DI provider | — |
| `api/routes/analytics.py` | `from options_arena.data import ...` | 6 analytics queries + 3 calibration | Analytics, Debate |
| `api/routes/debate.py` | `from options_arena.data import ...` | save/get debate, scores | Debate, Scan |
| `api/routes/export.py` | `from options_arena.data import ...` | `get_debate_by_id` | Debate |
| `api/routes/market.py` | `from options_arena.data import ...` | `get_all_ticker_metadata` | Metadata |
| `api/routes/scan.py` | `from options_arena.data import ...` | scan CRUD + contracts | Scan, Analytics |
| `api/routes/ticker.py` | `from options_arena.data import ...` | score history, trending | Scan |
| `api/routes/universe.py` | `from options_arena.data import ...` | metadata CRUD | Metadata |
| `agents/orchestrator.py` | `from ...data.repository import ...` | save_debate, predictions, weights | Debate |
| `scan/pipeline.py` | `from options_arena.data import ...` | 4 saves (commit=False) + commit + metadata | Scan, Analytics, Metadata |
| `services/outcome_collector.py` | `from ...data.repository import ...` | contracts_needing, save_outcomes, summary | Analytics |
| `cli/commands.py` | `from options_arena.data import ...` | scans, debates, metadata | Scan, Debate, Metadata |
| `cli/outcomes.py` | `from options_arena.data import ...` | calibration, `repo._db.conn` direct | Debate, Analytics |
| `cli/rendering.py` | `from ...data.repository import DebateRow` | DebateRow only | — |

### Direct `data.repository` Imports (Bypass `__init__.py`)

Production: `agents/orchestrator.py`, `services/outcome_collector.py`, `cli/rendering.py`
Tests: All 12 `tests/unit/data/` files + 4 API test files + 2 integration test files

All safe — `repository.py` continues to define `Repository` and `DebateRow` after decomposition.

## Potential Conflicts

- **No existing mixin pattern**: This is the first use of mixin/multiple-inheritance composition
  in the codebase. No precedent to follow. Risk: developers unfamiliar with MRO. Mitigation:
  keep it simple — all mixins inherit `RepositoryBase`, no cooperative `super()` calls needed.

- **`cli/outcomes.py` accesses `repo._db.conn` directly** (line 104, suppressed with `# noqa: SLF001`):
  Pre-existing leaky abstraction. Works fine under mixins since `_db` is on `RepositoryBase`.
  Not a blocking issue but worth noting.

- **5 test files access `repo._db.conn` directly** (`test_analytics_queries.py`,
  `test_repository_metadata.py`, `test_agent_calibration_queries.py` ×3,
  `test_calibration_pipeline.py` ×2): All safe since `_db` stays on `RepositoryBase`, accessible
  on any `Repository` instance.

- **`get_last_debate_dates()` domain ambiguity**: Listed in "Score history" section, queries
  `ai_theses` (debate table), but used by scan-related API conftest. PRD assigns to `ScanMixin`.
  Acceptable since it's a read-only cross-table query that logically serves the scan pipeline.

- **`get_last_debate_dates()` returns `dict[str, datetime]`**: Only public method violating the
  "no raw dicts" rule. Pre-existing issue, not introduced by this refactor. Could be fixed
  opportunistically but is out of scope per PRD.

- **40-model import block distribution**: The monolith imports ~40 models. Each mixin will need
  only its subset. Mechanical but must be done carefully to avoid missing imports. No circular
  import risk since mixins only import from `models/` and `_base`.

## Open Questions

- **5 mixins vs 4?** The PRD groups calibration (4 methods) into `DebateMixin`. The agents found
  calibration queries JOIN `agent_predictions` (created by `save_agent_predictions` in DebateMixin)
  AND `contract_outcomes` (managed by AnalyticsMixin). A separate `_calibration.py` could be
  cleaner. Decision: follow the PRD (4 mixins) — calibration is closer to debate domain.

- **`DebateRow` location**: The PRD says "stays in `repository.py`". Should it move to `_debate.py`
  and be re-exported from `repository.py`? Either works. The simpler approach (keep in
  `repository.py`) avoids any import chain issues.

## Recommended Architecture

Follow the PRD exactly — 4 mixin files + 1 base:

```
src/options_arena/data/
    _base.py         # RepositoryBase: __init__(db), commit(), _db declaration
    _scan.py         # ScanMixin(RepositoryBase): 12 methods (~350 LOC)
    _debate.py       # DebateMixin(RepositoryBase): 10 methods (~400 LOC)
    _analytics.py    # AnalyticsMixin(RepositoryBase): 18 methods (~650 LOC)
    _metadata.py     # MetadataMixin(RepositoryBase): 7 methods (~200 LOC)
    repository.py    # Repository(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin) + DebateRow
    database.py      # Unchanged
    __init__.py      # Unchanged
```

MRO: `Repository → ScanMixin → DebateMixin → AnalyticsMixin → MetadataMixin → RepositoryBase → object`

Key implementation notes:
1. Each mixin inherits `RepositoryBase` — mypy resolves `self._db: Database` across all mixins
2. No cooperative `super().__init__()` in mixins — `Repository.__init__` delegates to `RepositoryBase.__init__`
3. `DebateRow` dataclass stays in `repository.py` — preserves all 8 consumer import paths
4. Leading-underscore filenames (`_scan.py`) signal internal implementation detail
5. `repository.py` becomes ~30 LOC: imports, `Repository` class definition, `DebateRow` dataclass

## Test Strategy Preview

### Test File Inventory (~174 tests across 18 files)

| File | Count | Domain |
|------|-------|--------|
| `tests/unit/data/test_repository.py` | 36 | Core scan + debate CRUD |
| `tests/unit/data/test_repository_v2.py` | 7 | Structured agent JSON |
| `tests/unit/data/test_repository_dimensional.py` | 12 | Dimensional scores |
| `tests/unit/data/test_repository_metadata.py` | 13 | Metadata CRUD |
| `tests/unit/data/test_analytics_repository.py` | 13 | Contracts + normalization |
| `tests/unit/data/test_outcome_repository.py` | 8 | Outcomes |
| `tests/unit/data/test_agent_calibration_queries.py` | 13 | Calibration |
| `tests/unit/data/test_agent_predictions.py` | 9 | Agent predictions |
| `tests/unit/data/test_analytics_queries.py` | 16 | Analytics queries |
| `tests/unit/data/test_market_context_persistence.py` | 6 | Market context JSON |
| `tests/unit/data/test_industry_group_persistence.py` | 4 | Industry group |
| `tests/unit/api/test_repository_debates.py` | 3 | Debate via in-memory DB |
| `tests/unit/data/test_migration.py` | 5 | Schema verification |
| `tests/unit/data/test_migration_019.py` | 4 | Migration 019 |
| `tests/unit/data/test_migration_020.py` | 6 | Migration 020 |
| `tests/unit/data/test_database.py` | 10 | Database lifecycle |
| `tests/integration/test_metadata_index.py` | ~5 | Metadata integration |
| `tests/integration/test_calibration_pipeline.py` | 9 | Calibration E2E |

### Fixture Pattern (Universal)

```python
@pytest_asyncio.fixture
async def db() -> Database:
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()

@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)
```

Every test file defines its own local fixtures. No shared conftest for Repository.
All tests construct `Repository(db)` — mixin composition is transparent.

### API Mock Pattern

`tests/unit/api/conftest.py` creates `MagicMock()` for `mock_repo` stubbing 11 methods.
Method names preserved by MRO — no changes needed.

### Zero Test Modifications Required

All tests import `Repository` from `options_arena.data.repository` or `options_arena.data`.
Both import paths continue to resolve. `DebateRow` stays in `repository.py`. `_db` attribute
stays on `RepositoryBase`, accessible on all `Repository` instances.

## Estimated Complexity

**M (Medium)** — Mechanical extraction with well-defined boundaries.

Justification:
- Clear domain boundaries already marked by comment banners
- Zero logic changes — pure code movement
- Zero consumer changes — MRO preserves all method signatures
- No new abstractions beyond `RepositoryBase`
- 47 methods to redistribute across 4 files (largest is ~650 LOC)
- Import block distribution requires care but is mechanical
- Risk is low: existing tests provide comprehensive regression coverage (~174 tests)
- First mixin pattern in codebase adds minor learning curve
