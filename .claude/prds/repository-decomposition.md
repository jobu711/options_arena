---
name: repository-decomposition
description: Decompose the 1,769-line Repository monolith into domain-specific mixin classes
status: planned
created: 2026-03-09T18:40:26Z
---

# PRD: repository-decomposition

## Executive Summary

Split the monolithic `Repository` class (1,769 LOC, 47 methods, 8 domains) into focused
mixin classes using Python multiple inheritance. The public `Repository` API remains
identical — zero consumer changes across `api/`, `cli/`, `scan/`, `agents/`, and `services/`.

## Problem Statement

### What problem are we solving?

`src/options_arena/data/repository.py` is the single largest file and #1 risk hotspot in
the codebase. At 1,769 lines with 47 methods spanning 8 unrelated domains (scan persistence,
debate storage, analytics queries, metadata CRUD, agent calibration, etc.), it violates the
Single Responsibility Principle and creates practical problems:

- Every data-layer change touches the same file, causing merge conflicts
- Impossible to test one domain in isolation without loading all 47 methods
- New developers must read 1,769 lines to understand any single domain
- Code review burden — changes to analytics queries require reviewing scan persistence context

### Why is this important now?

Recent epics added significant surface area: outcome analytics (12 methods), metadata index
(8 methods), agent calibration (4 methods), and debate persistence grew to handle 8 agent
types. The class has grown past its natural boundaries. Each new feature will make the
problem worse.

## User Stories

- **As a developer**, I want each persistence domain in its own file so I can read and modify
  scan persistence without scrolling past 1,000 lines of unrelated analytics queries.
- **As a developer**, I want to run tests against a specific domain's repository methods
  without importing the entire monolith.
- **As a developer working on a new epic**, I want to add persistence methods to a focused
  ~200-400 LOC file rather than appending to a 1,769-line monolith.

## Architecture & Design

### Chosen Approach: Mixin Inheritance (Zero Consumer Changes)

Each of the 8 existing comment-banner groups is extracted into a mixin class in its own file.
All mixins inherit from `RepositoryBase` which declares `_db: Database` and `commit()`. The
public `Repository` class becomes a thin composition via multiple inheritance:

```python
# data/repository.py (~30 lines)
class Repository(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin):
    def __init__(self, db: Database) -> None:
        self._db = db
```

Every consumer still imports `Repository` — nothing changes. MRO handles method resolution.
mypy sees `_db: Database` on `RepositoryBase` and is satisfied across all mixins.

**Why mixins over standalone classes or facades:**
- Zero delegation code (no forwarding methods)
- Zero consumer changes (no import updates)
- Full mypy --strict compatibility via `RepositoryBase._db` declaration
- Atomic commit pattern preserved (shared `self._db` instance)
- Leading-underscore files signal internal implementation detail

### Module Changes

**New files** (all under `src/options_arena/data/`):

| File | Class | Methods | LOC (est.) | Tables Operated |
|------|-------|---------|-----------|-----------------|
| `_base.py` | `RepositoryBase` | `commit()` | ~20 | -- |
| `_scan.py` | `ScanMixin` | 12 | ~350 | `scan_runs`, `ticker_scores` |
| `_debate.py` | `DebateMixin` | 10 | ~400 | `ai_theses`, `agent_predictions`, `auto_tune_weights` |
| `_analytics.py` | `AnalyticsMixin` | 18 | ~650 | `recommended_contracts`, `contract_outcomes`, `normalization_metadata` |
| `_metadata.py` | `MetadataMixin` | 7 | ~200 | `ticker_metadata` |

**Modified files:**
- `data/repository.py` — gutted to ~30 lines: imports mixins, defines `Repository`, keeps `DebateRow`
- `data/__init__.py` — unchanged (`Repository`, `DebateRow`, `Database` re-exports stay)

**Untouched:** All consumers (`api/`, `cli/`, `scan/`, `agents/`, `services/`)

### Data Models

No new models. `DebateRow` dataclass stays in `repository.py` (re-exported via `__init__.py`).
All existing Pydantic models imported by mixins from `models/`.

`RepositoryBase` structure:
```python
class RepositoryBase:
    _db: Database

    async def commit(self) -> None:
        await self._db.conn.commit()
```

### Core Logic: Method Grouping

**ScanMixin (12 methods)** — Scan/Score (9) + Score History (3):
- `save_scan_run`, `save_ticker_scores`, `get_latest_scan`, `get_scan_by_id`,
  `get_scores_for_scan`, `get_recent_scans`, `_row_to_scan_run`, `_row_to_ticker_score`
- `get_score_history`, `get_trending_tickers`, `get_last_debate_dates`
- Rationale: Score History queries JOIN `scan_runs` + `ticker_scores` — same tables as scan CRUD

**DebateMixin (10 methods)** — Debate (6) + Agent Calibration (4):
- `save_debate`, `save_agent_predictions`, `get_debate_by_id`, `get_recent_debates`,
  `get_debates_for_ticker`, `_row_to_debate_row`
- `get_agent_accuracy`, `get_agent_calibration`, `get_latest_auto_tune_weights`,
  `save_auto_tune_weights`
- Rationale: Calibration queries JOIN `agent_predictions` created by `save_agent_predictions`

**AnalyticsMixin (18 methods)** — Contracts/Normalization (7) + Outcomes (5) + Queries (6):
- `save_recommended_contracts`, `get_contracts_for_scan`, `get_contracts_for_ticker`,
  `save_normalization_stats`, `get_normalization_stats`, `_row_to_recommended_contract`,
  `_row_to_normalization_stats`
- `save_contract_outcomes`, `get_outcomes_for_contract`, `get_contracts_needing_outcomes`,
  `has_outcome`, `_row_to_contract_outcome`
- `get_win_rate_by_direction`, `get_score_calibration`, `get_indicator_attribution`,
  `get_optimal_holding_period`, `get_delta_performance`, `get_performance_summary`
- Rationale: All revolve around `recommended_contracts` + `contract_outcomes` tables

**MetadataMixin (7 methods)** — Ticker Metadata:
- `upsert_ticker_metadata`, `upsert_ticker_metadata_batch`, `get_ticker_metadata`,
  `get_all_ticker_metadata`, `get_stale_tickers`, `get_metadata_coverage`,
  `_row_to_ticker_metadata`
- Rationale: Self-contained `ticker_metadata` CRUD with no cross-domain joins

### MRO

`Repository -> ScanMixin -> DebateMixin -> AnalyticsMixin -> MetadataMixin -> RepositoryBase -> object`

## Requirements

### Functional Requirements

1. All 47 public methods accessible via `Repository` instance with identical signatures
2. `DebateRow` importable from `options_arena.data` unchanged
3. `scan/pipeline.py` atomic commit pattern works: `save_*(commit=False)` then `commit()`
4. `Database` lifecycle (connect/close) unchanged
5. All ~4,200 existing tests pass without modification

### Non-Functional Requirements

1. Each mixin file under 650 LOC (largest is AnalyticsMixin)
2. `repository.py` reduced from 1,769 to ~30 LOC
3. mypy --strict passes on all new files
4. ruff lint/format clean
5. No runtime performance regression (mixin method lookup is O(1) via MRO caching)

## API / CLI Surface

N/A — pure internal refactor. No command, endpoint, or UI changes.

## Testing Strategy

**Existing tests pass unchanged**: All repository tests import `Repository` and use
`Database(":memory:")`. Since the public class and all method signatures are identical,
every existing test works without modification.

**New coverage (blocking):**
- Smoke test verifying `Repository` has all 40 public methods (introspection guard)
- Import test verifying `from options_arena.data import Repository, DebateRow, Database`

**Verification:**
- `uv run ruff check . --fix && uv run ruff format .`
- `uv run mypy src/ --strict`
- `uv run pytest tests/ -n auto -q`

**Edge cases to verify:**
- `commit()` accessible via `Repository` (MRO through `RepositoryBase`)
- No circular imports between mixin files (they only import from `models/` and `_base`)
- `DebateRow` import path unchanged

## Success Criteria

1. `repository.py` reduced from 1,769 LOC to ~30 LOC
2. All ~4,200 tests pass (zero test modifications)
3. All consumers unchanged (zero import changes in `api/`, `cli/`, `scan/`, `agents/`, `services/`)
4. mypy --strict clean
5. ruff clean
6. Each domain file independently readable without cross-domain context

## Constraints & Assumptions

- Python MRO (C3 linearization) handles diamond inheritance correctly with `RepositoryBase`
- mypy --strict resolves `self._db` via `RepositoryBase` annotation across all mixins
- No mixin needs to call methods from another mixin (confirmed: zero cross-domain calls)
- `DebateRow` stays in `repository.py` (not moved to a mixin) since it's a public re-export

## Out of Scope

- Database schema changes or new migrations
- Splitting `Database` class (it's already focused at ~80 LOC)
- Protocol/interface abstractions for repository methods
- Consumer-side changes (DI refactoring, separate repo injection)
- Moving `DebateRow` to `models/` (separate concern, could be a follow-up)

## Dependencies

- No external dependencies
- No new packages
- Internal only: `data/database.py`, `models/` (existing imports)
