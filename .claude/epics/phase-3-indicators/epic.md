---
name: phase-3-indicators
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 3: Indicators Cherry-Pick

## Overview

Port all 6 indicator files and their tests from v3. These are mathematically verified, have the largest test count (~250), and have zero project dependencies (pandas/numpy only). Pure copy + import update — no logic changes.

## Scope

### PRD Requirements Covered
FR-I1, FR-I2

### Deliverables

**`src/options_arena/indicators/`:**

- `oscillators.py` — RSI, Stochastic RSI, Williams %R
- `trend.py` — ADX (Wilder's smoothing), ROC, Supertrend
- `volatility.py` — Bollinger Band Width, ATR%, Keltner Channel Width
- `volume.py` — OBV, Accumulation/Distribution, Relative Volume
- `moving_averages.py` — SMA Alignment, VWAP Deviation
- `options_specific.py` — IV Rank, IV Percentile, Put/Call Ratio, Max Pain Distance
- `__init__.py` — Re-export all indicator functions

**Changes from v3:**
- `from Option_Alpha.` → `from options_arena.` (import paths only)
- No math changes, no API changes, no signature changes

**Convention (enforced by tests):**
- Input: `pd.Series` or `pd.DataFrame`
- Output: `pd.Series` or `pd.DataFrame`
- Warmup period returns `NaN` — never fill, backfill, or drop
- `InsufficientDataError` if input length < minimum required
- Vectorized operations only (no Python loops for math)

**Tests (`tests/unit/indicators/`):**
- Cherry-pick all indicator tests from v3
- Update imports to `options_arena.indicators.*`
- ~250 tests total (largest module by test count)

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models — only needs `InsufficientDataError` from `utils/exceptions.py`)
- **Blocks**: Epic 7 (scan pipeline — `IndicatorSpec` registry references indicator functions)
- **Parallelizable**: Can run in parallel with Epics 2, 5, 6 after Epic 1 completes

## Key Decisions
- Zero logic changes from v3 — trust the mathematical verification
- If any v3 test fails after port, investigate before modifying indicator code
- `indicators/` has no dependency on `models/` (except exceptions) — pure math layer

## Estimated Tests: ~250
