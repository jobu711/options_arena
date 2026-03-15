---
name: comp-audit
status: completed
created: 2026-03-15T16:38:10Z
progress: 100%
updated: 2026-03-15T21:00:00Z
completed: 2026-03-15T21:00:00Z
prd: .claude/prds/comp-audit.md
github: https://github.com/jobu711/options_arena/issues/523
---

# Epic: comp-audit

## Overview

Integrate 7 cherry-picked features from the ai-hedge-fund competitive audit into
Options Arena: Hurst exponent regime classification, risk-adjusted performance metrics,
distinctive agent personas, deterministic constraint pre-checks, volatility-regime
position sizing, multi-methodology fair-value estimation, and portfolio correlation
matrix. All implementations from scratch using existing dependencies only (numpy,
pandas, scipy). Delivered in 3 waves with ~85 new tests.

## Architecture Decisions

- **`analysis/` package** is the home for new computation modules (performance, position
  sizing, valuation, correlation). Package directory exists but has no Python files —
  create `__init__.py` and 4 new modules. Boundary: imports `models/`, `pricing/dispatch`,
  `scipy` only — no I/O, no API calls.
- **Hurst goes in `indicators/`** (not `analysis/`) — follows `hv_estimators.py` pattern
  (pandas in, scalar out, no Pydantic models).
- **Constraint pre-check in `agents/constraints.py`** — runs before agent invocation,
  injects warnings into prompts. Deterministic, no LLM calls.
- **New model files**: `models/valuation.py`, `models/correlation.py` for dedicated
  model namespaces. Smaller additions go into existing model files.
- **No new migrations** — all data computed on the fly from existing tables.
- **No new dependencies** — numpy, pandas, scipy, existing stack only.
- **Valuation degrades gracefully** — depends on `fd_*` fields from FinancialDatasets
  epic #393. Adds model fields now (accepting None), implements computation logic,
  population deferred to #393.

## Technical Approach

### Indicators Layer
- `indicators/hurst.py`: Rescaled range (R/S) analysis → Hurst exponent (Mandelbrot & Wallis 1969)
- Integrated into `IndicatorSignals` model and `INDICATOR_WEIGHTS` (0.02, "regime" category)

### Analysis Layer (New Package)
- `analysis/performance.py`: Sharpe, Sortino, max drawdown from `contract_outcomes` table
- `analysis/position_sizing.py`: 4-tier vol bucketing with correlation adjustment
- `analysis/valuation.py`: 4-model composite (Owner Earnings DCF, 3-Stage DCF, EV/EBITDA, Residual Income)
- `analysis/correlation.py`: Pairwise Pearson correlation from daily close prices

### Agent Layer
- 6 prompt files get persona identity paragraphs (~80 tokens each)
- `agents/constraints.py`: deterministic constraint checker with prompt injection
- `DebateDeps` extended with `constraint_warnings` field
- `render_context_block()` extended with position sizing + valuation + constraint sections

### Data / API / CLI
- `AnalyticsMixin.get_risk_adjusted_metrics()` — SQL query on existing `contract_outcomes`
- 2 new API endpoints: `/api/analytics/risk-metrics`, `/api/analytics/correlation`
- 2 new CLI subcommands: `outcomes risk-metrics`, `outcomes correlation`

## Implementation Strategy

### Wave 1 — Foundation (parallel, no internal dependencies)
- Task 1: Hurst exponent indicator + scoring integration
- Task 2: Risk-adjusted performance metrics (analysis/ package init here)
- Task 3: Agent persona framing (prompt-only, lowest risk)

### Wave 2 — Analysis Core (after Wave 1)
- Task 4: Constraint pre-check + agent prompt injection
- Task 5: Position sizing algorithm + agent context rendering

### Wave 3 — Data-Heavy (after Wave 2)
- Task 6: Multi-methodology valuation + fundamental agent integration
- Task 7: Portfolio correlation matrix + API/CLI + feeds into position sizing

### Risk Mitigation
- **Weight sum guard**: `roc` 0.03→0.02 + `put_call_ratio` 0.03→0.02 + `hurst_exponent` 0.02 = net 0.00 change. Must be atomic edit.
- **MarketContext validator list**: Every new `float | None` field added to `validate_optional_finite`.
- **DebateDeps dual modification**: Tasks 4 and 5 both modify `_parsing.py` — Wave 2 ordering resolves.
- **FD data availability**: Valuation returns None when `fd_*` fields absent. No hard dependency.
- **analysis/ CLAUDE.md**: Current content is mislabeled (describes scoring/). Will rewrite for analysis/ constraints.

## Task Breakdown Preview

- [ ] Task 1: Hurst Exponent Indicator (FR-C1) — `indicators/hurst.py`, model field, scoring weight, ~10 tests
- [ ] Task 2: Risk-Adjusted Performance Metrics (FR-C2) — `analysis/performance.py`, `__init__.py`, model, data query, API endpoint, CLI subcommand, ~10 tests
- [ ] Task 3: Agent Persona Framing (FR-C3) — 6 prompt file edits, version bumps, ~6 tests
- [ ] Task 4: Constraint Pre-Check (FR-C4) — `agents/constraints.py`, enums, model, DebateDeps integration, ~12 tests
- [ ] Task 5: Position Sizing Algorithm (FR-C5) — `analysis/position_sizing.py`, config, MarketContext fields, agent rendering, ~12 tests
- [ ] Task 6: Multi-Methodology Valuation (FR-C6) — `analysis/valuation.py`, `models/valuation.py`, enums, MarketContext fields, fundamental agent prompt, ~20 tests
- [ ] Task 7: Portfolio Correlation Matrix (FR-C7) — `analysis/correlation.py`, `models/correlation.py`, API endpoint, CLI subcommand, feeds into Task 5, ~15 tests

## Dependencies

### External
- FinancialDatasets epic #393 for `fd_*` field population (Task 6 gracefully degrades without it)
- FRED service for risk-free rate (existing fallback: 5%)

### Internal (Wave ordering)
- Wave 2 depends on Wave 1 completion (analysis/ package init from Task 2)
- Wave 3 depends on Wave 2 (Task 7 correlation feeds into Task 5 position sizing)
- Tasks within each wave are independent and parallelizable

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Hurst computed for tickers with 200+ bars | >95% |
| Sharpe/Sortino available with ≥30 closed outcomes | Yes |
| Constraint violations caught (expired/illiquid) | 100% |
| Position size in debate output (when IV available) | 100% |
| Correlation matrix for 2+ tickers with 30+ overlap | Yes |
| Valuation signal with FD data present | >50% of tickers |
| Existing 4,522 tests pass | 100% (zero regressions) |
| New tests added | ~85 across 10 test files |
| `INDICATOR_WEIGHTS` sum == 1.0 | Import-time guard passes |

## Estimated Effort

- **Overall**: XL — 7 tasks across 3 waves
- **New files**: 9 (1 indicator, 4 analysis, 2 models, 1 agents, 1 analysis init)
- **Modified files**: ~31 across models, scoring, agents, data, API, CLI
- **New tests**: ~85 across 10 test files
- **Critical path**: Wave 1 → Wave 2 → Wave 3 (sequential waves, parallel within)

## Tasks Created

- [ ] #524 - Hurst Exponent Indicator (parallel: true) — Wave 1
- [ ] #528 - Risk-Adjusted Performance Metrics (parallel: true) — Wave 1
- [ ] #529 - Agent Persona Framing (parallel: true) — Wave 1
- [ ] #530 - Constraint Pre-Check (parallel: false) — Wave 2
- [ ] #525 - Position Sizing Algorithm (parallel: false, depends: #528) — Wave 2
- [ ] #526 - Multi-Methodology Valuation (parallel: false, depends: #528, #525) — Wave 3
- [ ] #527 - Portfolio Correlation Matrix (parallel: false, depends: #528, #525) — Wave 3

Total tasks: 7
Parallel tasks: 3 (Wave 1)
Sequential tasks: 4 (Waves 2-3)

## Test Coverage Plan

Total test files planned: 10
Total test cases planned: ~85

| Test File | Task | Cases |
|-----------|------|-------|
| `tests/unit/indicators/test_hurst.py` | #524 | ~10 |
| `tests/unit/scoring/test_hurst_integration.py` | #524 | ~5 |
| `tests/unit/analysis/test_performance.py` | #528 | ~10 |
| `tests/unit/data/test_risk_metrics_query.py` | #528 | ~5 |
| `tests/unit/agents/test_personas.py` | #529 | ~6 |
| `tests/unit/agents/test_constraints.py` | #530 | ~12 |
| `tests/unit/analysis/test_position_sizing.py` | #525 | ~12 |
| `tests/unit/analysis/test_valuation.py` | #526 | ~20 |
| `tests/unit/models/test_valuation_models.py` | #526 | ~5 |
| `tests/unit/analysis/test_correlation.py` | #527 | ~15 |
