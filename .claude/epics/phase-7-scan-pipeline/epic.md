---
name: phase-7-scan-pipeline
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 7: Scan Pipeline

## Overview

Build the `scan/` package: the core orchestration module that ties everything together. Replaces the monolithic 430-line `cli.py` scan function with a testable, cancellable, progress-reporting `ScanPipeline` class with 4 async phases.

## Scope

### PRD Requirements Covered
FR-SP1, FR-SP2, FR-SP3, FR-SP4, FR-SP5

### Deliverables

**`src/options_arena/scan/`:**

- `progress.py`:
  - `CancellationToken` — instance-scoped cancellation (replaces global `_scan_cancelled`). `cancel()` method, `is_cancelled` property, checked between phases.
  - `ProgressCallback` — `Protocol` class with `__call__(phase: str, current: int, total: int)`. Framework-agnostic (CLI uses Rich, tests use no-op, future web UI uses WebSocket).

- `indicators.py`:
  - `IndicatorSpec` — `NamedTuple(name: str, func: Callable, input_shape: str)` where `input_shape` is `"series"` or `"dataframe"`
  - `INDICATOR_REGISTRY: list[IndicatorSpec]` — data-driven list of all 18 indicators
  - `compute_indicators(ohlcv_df, registry) -> dict[str, pd.Series]` — generic loop with isolated per-indicator try/except (one failure doesn't crash others)

- `models.py` — Pipeline-internal typed models:
  - `UniverseResult` — tickers with OHLCV data
  - `ScoringResult` — tickers with scores and direction
  - `OptionsResult` — tickers with recommended contracts
  - `ScanResult` — final output with all results + metadata

- `pipeline.py` — `ScanPipeline`:
  - Constructor: `(settings: AppSettings, services: ..., repository: Repository)`
  - `async run(config: ScanConfig, token: CancellationToken, progress: ProgressCallback) -> ScanResult`
  - **Phase 1**: Universe fetch + OHLCV (via `services/`)
  - **Phase 2**: Indicators (via `scan/indicators.py`) + normalization + composite scoring + direction (via `scoring/`)
  - **Phase 3**: Liquidity pre-filter ($10M avg dollar volume, $10 min price) → top-N by score → fetch option chains (via `services/`) → contract selection (via `scoring/contracts.py`)
  - **Phase 4**: Persist to SQLite (via `data/repository.py`)
  - Cancellation check between each phase
  - `ProgressCallback` invoked at each phase transition

- `__init__.py` — Re-export `ScanPipeline`, `CancellationToken`, `ProgressCallback`, `ScanResult`

**Tests (`tests/unit/scan/`):**
- IndicatorSpec registry: all 18 entries present, correct function references
- `compute_indicators`: isolated failure (one bad indicator doesn't affect others), NaN handling
- CancellationToken: cancel mid-pipeline, verify early exit
- ProgressCallback: invocation order (phase 1 → 2 → 3 → 4)
- Pipeline phases: mock services, verify data flow between phases
- ScanResult: correct aggregation of results
- ~80 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models), Epic 3 (indicators), Epic 4 (scoring), Epic 5 (services), Epic 6 (data)
- **Blocks**: Epic 8 (CLI)

## Key Decisions
- `IndicatorSpec` registry is a flat list, not a class hierarchy — keeps it simple
- Per-indicator try/except: one failing indicator logs a warning and continues
- Pipeline phases are methods on `ScanPipeline`, not separate classes
- `CancellationToken` is passed through, not global state

## Estimated Tests: ~80
