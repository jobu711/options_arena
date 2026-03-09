---
name: repository-decomposition
status: backlog
created: 2026-03-09T19:03:07Z
progress: 0%
prd: .claude/prds/repository-decomposition.md
github: https://github.com/jobu711/options_arena/issues/417
---

# Epic: repository-decomposition

## Overview

Decompose the 1,769-line `Repository` monolith in `src/options_arena/data/repository.py` into
4 domain-specific mixin classes plus a `RepositoryBase`. The public `Repository` class becomes a
thin MRO composition (~30 LOC). Zero consumer changes — all imports, method signatures, and
`DebateRow` re-exports remain identical.

## Architecture Decisions

- **Mixin inheritance over standalone repos or facade**: Zero delegation code, zero consumer
  changes, full mypy `--strict` compatibility via `RepositoryBase._db` declaration. The public
  `Repository` class simply inherits all mixins.
- **4 mixins (not 5)**: Calibration (4 methods) stays with `DebateMixin` — its queries JOIN
  `agent_predictions` created by `save_agent_predictions`. Follows PRD decision.
- **Leading-underscore filenames** (`_scan.py`, `_base.py`): Signals internal implementation.
  No consumer ever imports from these files directly.
- **`DebateRow` stays in `repository.py`**: Preserves all 8 consumer import paths without change.
- **No cooperative `super().__init__()`**: `Repository.__init__` calls `RepositoryBase.__init__`
  directly. Mixins declare no `__init__`.

## Technical Approach

### File Structure (all under `src/options_arena/data/`)

| New File | Class | Methods | Est. LOC | Tables |
|----------|-------|---------|----------|--------|
| `_base.py` | `RepositoryBase` | `commit()` | ~20 | — |
| `_scan.py` | `ScanMixin(RepositoryBase)` | 12 | ~350 | `scan_runs`, `ticker_scores` |
| `_debate.py` | `DebateMixin(RepositoryBase)` | 10 | ~400 | `ai_theses`, `agent_predictions`, `auto_tune_weights` |
| `_analytics.py` | `AnalyticsMixin(RepositoryBase)` | 18 | ~650 | `recommended_contracts`, `contract_outcomes`, `normalization_metadata` |
| `_metadata.py` | `MetadataMixin(RepositoryBase)` | 7 | ~200 | `ticker_metadata` |

### Modified Files

- `data/repository.py` — gutted to ~30 LOC: imports mixins, defines `Repository` class, keeps `DebateRow`
- `data/__init__.py` — unchanged (re-exports `Repository`, `DebateRow`, `Database`)

### Unchanged

- All consumers: `api/`, `cli/`, `scan/`, `agents/`, `services/`
- `data/database.py`, `data/migrations/`
- All ~4,200 existing tests

### MRO

```
Repository → ScanMixin → DebateMixin → AnalyticsMixin → MetadataMixin → RepositoryBase → object
```

### Method Distribution

**ScanMixin** (12): `save_scan_run`, `save_ticker_scores`, `get_latest_scan`, `get_scan_by_id`,
`get_scores_for_scan`, `get_recent_scans`, `_row_to_scan_run`, `_row_to_ticker_score`,
`get_score_history`, `get_trending_tickers`, `get_last_debate_dates`

**DebateMixin** (10): `save_debate`, `save_agent_predictions`, `get_debate_by_id`,
`get_recent_debates`, `get_debates_for_ticker`, `_row_to_debate_row`, `get_agent_accuracy`,
`get_agent_calibration`, `get_latest_auto_tune_weights`, `save_auto_tune_weights`

**AnalyticsMixin** (18): `save_recommended_contracts`, `get_contracts_for_scan`,
`get_contracts_for_ticker`, `save_normalization_stats`, `get_normalization_stats`,
`_row_to_recommended_contract`, `_row_to_normalization_stats`, `save_contract_outcomes`,
`get_outcomes_for_contract`, `get_contracts_needing_outcomes`, `has_outcome`,
`_row_to_contract_outcome`, `get_win_rate_by_direction`, `get_score_calibration`,
`get_indicator_attribution`, `get_optimal_holding_period`, `get_delta_performance`,
`get_performance_summary`

**MetadataMixin** (7): `upsert_ticker_metadata`, `upsert_ticker_metadata_batch`,
`get_ticker_metadata`, `get_all_ticker_metadata`, `get_stale_tickers`,
`get_metadata_coverage`, `_row_to_ticker_metadata`

## Implementation Strategy

Pure mechanical extraction — no logic changes, no new abstractions, no consumer modifications.

### Execution Order

1. **Foundation**: Create `_base.py` with `RepositoryBase` (everything depends on this)
2. **Extraction** (parallelizable): Create all 4 mixin files, each importing only from
   `models/` and `_base`. Copy methods verbatim from `repository.py` with their imports.
3. **Composition**: Slim `repository.py` to ~30 LOC MRO composition class + `DebateRow`
4. **Guard tests**: Add introspection test verifying all 47 public methods exist on `Repository`
5. **Verification**: Full lint + mypy + test suite pass

### Risk Mitigation

- **Import distribution**: Each mixin needs only its subset of the ~40 model imports. Verify
  no missing imports by running mypy on each file individually.
- **MRO correctness**: Python C3 linearization is deterministic. One introspection test guards
  against regressions.
- **`commit=False` pattern**: `commit()` on `RepositoryBase` is accessible through MRO. The
  4 write methods that accept `commit` parameter continue to work identically.

## Tasks Created

- [ ] #418 - Create RepositoryBase foundation (parallel: false)
- [ ] #419 - Extract ScanMixin and DebateMixin (parallel: true)
- [ ] #420 - Extract AnalyticsMixin and MetadataMixin (parallel: true)
- [ ] #421 - Slim repository.py to MRO composition (parallel: false)
- [ ] #422 - Add introspection guard test and final verification (parallel: false)

Total tasks: 5
Parallel tasks: 2 (#419 + #420 can run simultaneously)
Sequential tasks: 3 (#418 → #419/#420 → #421 → #422)
Estimated total effort: 7 hours

## Test Coverage Plan

Total test files planned: 1 (new guard test)
Total test cases planned: 5 (introspection, MRO, imports, dataclass, mixin inheritance)
Existing regression coverage: ~174 tests across 18 files (zero modifications)

## Dependencies

- **None**: Pure internal refactor. No new packages, no external services, no schema changes.
- **Prerequisite**: None — repository.py is stable with no in-flight changes.

## Success Criteria (Technical)

1. `repository.py` reduced from 1,769 LOC to ~30 LOC
2. All ~4,200 existing tests pass with zero modifications
3. All consumers unchanged (zero import changes in `api/`, `cli/`, `scan/`, `agents/`, `services/`)
4. `mypy --strict` clean on all new and modified files
5. `ruff check` + `ruff format` clean
6. Each mixin file independently readable without cross-domain context
7. `from options_arena.data import Repository, DebateRow, Database` unchanged
8. Introspection guard test confirms all 47 public methods present

## Estimated Effort

- **Size**: Medium (mechanical extraction, well-defined boundaries)
- **Tasks**: 5
- **Risk**: Low (174 existing tests provide comprehensive regression coverage)
- **Critical path**: Task 1 (foundation) → Tasks 2-3 (parallel) → Task 4 (composition) → Task 5 (verify)
