---
name: phase-4-scoring
status: backlog
created: 2026-02-22T08:50:13Z
updated: 2026-02-23T09:46:00Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/20
---

# Epic 4: Scoring Module

## Overview

Build the `scoring/` package: cherry-pick normalization, composite scoring, and direction classification from v3, then rewrite `contracts.py` to use `pricing/dispatch.py` as the sole source of Greeks.

## Scope

### PRD Requirements Covered
FR-S1, FR-S2, FR-S3, FR-S4

### Deliverables

**`src/options_arena/scoring/`:**

- `normalization.py` — Cherry-pick from v3:
  - Percentile-rank normalization with proper tie handling
  - Inversion for indicators where lower = better (e.g., ATR%)
  - Skip universally-missing indicators (renormalize weights)

- `composite.py` — Cherry-pick from v3:
  - Weighted geometric mean across indicator categories
  - Weights: Oscillators 0.27, Trend 0.20, Volatility 0.15, Volume 0.15, MA 0.10, Options 0.13

- `direction.py` — Cherry-pick from v3:
  - Direction classification: BULLISH / BEARISH / NEUTRAL
  - ADX/RSI/SMA signal aggregation with SMA alignment tiebreaker

- `contracts.py` — **Rewrite** (not cherry-pick):
  - Computes Greeks for ALL contracts via `pricing/dispatch.py` (sole source — yfinance provides none)
  - Uses `market_iv` from yfinance as IV solver seed when available; falls back to ATM IV estimate
  - Delta targeting: [0.20, 0.50] primary / [0.10, 0.80] fallback, closest-to-target selection
  - DTE filtering: [30, 60] days
  - Spread check with zero-bid exemption (bid=0/ask>0 skips spread check)
  - Accepts `exercise_style`, `dividend_yield`, `ScanConfig` for all thresholds
  - Removes v3 spot estimation hack (median strike proxy) — accepts real spot price

- `__init__.py` — Re-export public API

**Tests (`tests/unit/scoring/`):**
- Normalization: ties, inversion, universally-missing skip
- Composite: weight sum validation, geometric mean correctness
- Direction: all signal combinations, tiebreaker behavior
- Contracts: delta targeting, DTE filtering, spread exemption, Greeks computation integration, fallback behavior
- ~80 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models), Epic 2 (pricing — `contracts.py` uses `pricing/dispatch.py`)
- **Blocks**: Epic 7 (scan pipeline — Phase 2 scoring + Phase 3 contract selection)

## Key Decisions
- `contracts.py` is the only file rewritten (not cherry-picked) — the rest are pure ports
- Greeks are always computed locally — no conditional fallback for "missing yfinance Greeks"
- All thresholds come from `ScanConfig` / `PricingConfig` — no hardcoded magic numbers

## Estimated Tests: ~80

## Tasks Created
- [ ] #21 - Scoring package scaffold and CLAUDE.md (parallel: true)
- [ ] #25 - Implement normalization.py with percentile-rank scoring (depends: #21)
- [ ] #27 - Implement composite.py with weighted geometric mean scoring (depends: #21, #25)
- [ ] #22 - Implement direction.py with signal aggregation and tiebreaker (parallel: true, depends: #21)
- [ ] #24 - Implement contracts.py with Greeks dispatch and contract selection (parallel: true, depends: #21)
- [ ] #26 - Package integration, re-exports, and verification gate (depends: #25, #27, #22, #24)

Total tasks: 6
Parallel tasks: 3 (#21, #22, #24 can run independently after scaffold)
Sequential tasks: 3 (#25→#27 chain, #26 waits for all)
Estimated total effort: 39 hours

### Execution Order
```
#21 (scaffold) ──┬──→ #25 (normalization) ──→ #27 (composite) ──┐
                 ├──→ #22 (direction)      ─────────────────────┼──→ #26 (integration)
                 └──→ #24 (contracts)      ─────────────────────┘
```
