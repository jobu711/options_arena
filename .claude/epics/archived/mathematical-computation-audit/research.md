# Research: mathematical-computation-audit

## PRD Summary

Build a repeatable hybrid audit framework that validates all 87 mathematical functions across 4 modules (pricing, indicators, scoring, orchestration) against academic references and QuantLib cross-validation, stress-tests numerical stability with Hypothesis property-based testing, detects performance regressions via pytest-benchmark, and uses the quant-analyst agent as a discovery layer. This is a read-only audit — no source code modifications to pricing/, indicators/, scoring/, or agents/.

## Relevant Existing Modules

### Audit Targets (Source — Read-Only)

- `src/options_arena/pricing/` — BSM, BAW, Greeks, IV solvers, dispatch (17 functions)
  - `bsm.py`: bsm_price, bsm_greeks, bsm_vega, bsm_iv, bsm_second_order_greeks
  - `american.py`: american_price, american_greeks, american_iv, american_second_order_greeks + 3 internal helpers (_baw_auxiliary_params, _find_critical_price_call, _find_critical_price_put)
  - `dispatch.py`: option_price, option_greeks, option_iv, option_second_order_greeks
  - `_common.py`: validate_positive_inputs, intrinsic_value, is_itm, boundary_greeks

- `src/options_arena/indicators/` — 53 functions across 12 files
  - `oscillators.py` (3): rsi, stoch_rsi, williams_r
  - `trend.py` (7): roc, adx, supertrend, macd, compute_multi_tf_alignment, compute_rsi_divergence, compute_adx_exhaustion
  - `volatility.py` (3): bb_width, atr_percent, keltner_width
  - `volume.py` (4): _rolling_slope, obv_trend, relative_volume, ad_trend
  - `moving_averages.py` (2): sma_alignment, vwap_deviation
  - `options_specific.py` (6): iv_rank, iv_percentile, put_call_ratio_volume, put_call_ratio_oi, max_pain, + compute_pop/compute_optimal_dte/compute_spread_quality/compute_max_loss_ratio
  - `iv_analytics.py` (12): compute_iv_hv_spread, compute_iv_term_slope/shape, compute_put_skew, compute_call_skew, compute_skew_ratio, classify_vol_regime, compute_ewma_vol_forecast, compute_vol_cone_pctl, compute_vix_correlation, compute_expected_move, compute_expected_move_ratio
  - `hv_estimators.py` (3): compute_hv_parkinson, compute_hv_rogers_satchell, compute_hv_yang_zhang
  - `flow_analytics.py` (5): compute_gex, compute_oi_concentration, compute_unusual_activity, compute_max_pain_magnet, compute_dollar_volume_trend
  - `fundamental.py` (5): compute_earnings_em_ratio, compute_earnings_impact, compute_short_interest, compute_div_impact, compute_iv_crush_history
  - `regime.py` (7): classify_market_regime, compute_vix_term_structure, compute_risk_on_off, compute_sector_momentum, compute_rs_vs_spx, compute_correlation_regime_shift, compute_volume_profile_skew
  - `vol_surface.py` (6): compute_vol_surface, _fit_surface, _standalone_smile_curvature, _standalone_atm_iv, _standalone_implied_move, compute_surface_indicators

- `src/options_arena/scoring/` — 16 functions across 5 files
  - `normalization.py` (5): percentile_rank_normalize, invert_indicators, _invert_single, normalize_single_ticker, compute_normalization_stats
  - `composite.py` (2): composite_score, score_universe
  - `direction.py` (1): determine_direction
  - `contracts.py` (5): filter_contracts, select_expiration, compute_greeks, select_by_delta, recommend_contracts
  - `dimensional.py` (3): compute_dimensional_scores, apply_regime_weights, compute_direction_signal

- `src/options_arena/agents/orchestrator.py` — 5 mathematical functions
  - compute_agreement_score, _vote_entropy, _log_odds_pool, synthesize_verdict, classify_macd_signal

### Modules to Modify/Create

- `src/options_arena/models/enums.py` — Add AuditSeverity, AuditLayer StrEnums
- `src/options_arena/models/audit.py` — New file: AuditFinding, AuditReport, AuditLayerSummary
- `src/options_arena/models/config.py` — Add AuditConfig nested model to AppSettings
- `src/options_arena/cli/audit.py` — New file: `audit` subcommand group with `math` command
- `tests/audit/` — New directory: correctness, stability, performance test suites
- `tools/math_audit_report.py` — New: report generator
- `tools/generate_quantlib_baselines.py` — New: QuantLib baseline generator

**Grand total: 87 mathematical functions** (PRD estimated 66+ — actual count is higher due to internal helpers and recently added native quant functions).

## Existing Patterns to Reuse

### Test Patterns
- **Tolerance conventions**: `pytest.approx(rel=1e-6)` for put-call parity, `pytest.approx(abs=0.01)` for prices, `pytest.approx(rel=1e-4)` for Greeks/indicators
- **Academic citations in tests**: Hull (2018) Table 15.3 for BSM, BAW 1987 Table 1 for American options — already used in `test_bsm.py` and `test_american.py`
- **NaN warmup count tests**: Indicators validate that first N values are NaN (warmup period)
- **Stress grid parametrization**: `test_stress.py` uses `@pytest.mark.parametrize` with grids over S, K, T, r, q, σ (12K+ parametrized cases)
- **Pytest markers**: `@pytest.mark.critical`, `@pytest.mark.exhaustive` — add `audit_correctness`, `audit_stability`, `audit_performance`
- **Factories**: `tests/factories.py` provides `make_option_contract()`, `make_quote()`, `make_market_context()`

### CLI Pattern
- **Subcommand group**: `outcomes_app = typer.Typer(help="..."); app.add_typer(outcomes_app, name="outcomes")` in `cli/outcomes.py`
- **Async wrapper**: `def command() -> None: asyncio.run(_command_async())`
- **Service lifecycle**: Create AppSettings, services in command; close in `finally` block

### Report Pattern
- **Pure function**: `reporting/debate_export.py` takes Pydantic model → returns markdown string
- **No side effects**: Report generators don't write files — CLI handles file output

### Model Pattern
- **StrEnums in `enums.py`**: All categorical types (OptionType, SignalDirection, ExerciseStyle, etc.)
- **Frozen models**: `model_config = ConfigDict(frozen=True)` on all data snapshots
- **UTC validator**: Every `datetime` field must have `_validate_utc` field_validator
- **Re-export from `__init__.py`**: All public models accessible via `from options_arena.models import X`

## Existing Code to Extend

- `src/options_arena/models/enums.py` — Add 2 new StrEnums (AuditSeverity, AuditLayer)
- `src/options_arena/models/__init__.py` — Add re-exports for new audit models
- `src/options_arena/cli/app.py` — Register `audit_app` subcommand group
- `pyproject.toml` — Add 3 pytest markers + 3 dev dependencies

## Existing Code That Overlaps

- `tests/unit/test_audit_hardening.py` (280+ lines) — Tests model validators (Quote NaN/Inf rejection, OptionContract validators, composite score bounds). Covers validator hardening but NOT formula correctness.
- `tests/unit/models/test_audit_validators.py` (250+ lines) — Tests TickerInfo/ScanRun/RecommendedContract validators. Similar validator focus.
- `tests/unit/pricing/test_stress.py` — 12K+ parametrized stress cases. Overlaps with stability layer but doesn't use Hypothesis or systematic NaN injection.

**Action**: These tests should remain as-is. Audit tests are complementary — they add cross-validation, property-based testing, and performance benchmarking that these tests don't cover.

## Potential Conflicts

- **None identified**. The audit framework is entirely additive:
  - No existing `tests/audit/` directory
  - No existing `audit` CLI command
  - No existing `hypothesis` or `pytest-benchmark` usage
  - New pytest markers don't conflict with existing ones
  - Dev dependencies (hypothesis, pytest-benchmark) are safe additions

## Open Questions

1. **QuantLib on Python 3.13 + Windows**: Do QuantLib wheels exist for Python 3.13 on Windows? If not, baseline generation needs to run in a Docker container or CI Linux runner. Tests never require QuantLib at runtime — only the baseline generator does.

2. **Function registry approach**: Should the coverage meta-test discover functions via AST scanning, naming convention, or an explicit registry? AST scanning is most maintainable but requires parsing rules. The PRD mentions "decorator, naming convention, or explicit registry" — need to decide.

3. **Performance baseline platform variance**: Should benchmarks be stored per-platform (Windows vs Linux CI)? pytest-benchmark comparisons across platforms are unreliable due to hardware differences.

4. **analysis/ module scope**: The PRD lists `analysis/` as a target, but research shows this module is empty — vol surface and HV estimators are in `indicators/`. The 87-function inventory already covers everything in `indicators/vol_surface.py` and `indicators/hv_estimators.py`.

## Recommended Architecture

### Directory Structure
```
tests/audit/
├── __init__.py
├── conftest.py              # Coverage meta-test, Hypothesis profiles, shared fixtures
├── reference_data/
│   ├── pricing_known_values.json    # Academic: Hull, BAW tables
│   ├── quantlib_baselines.json      # QuantLib cross-validation (pre-generated)
│   ├── indicator_known_values.json  # Textbook indicator references
│   ├── scoring_known_values.json    # Scoring algorithm references
│   └── benchmarks/                  # pytest-benchmark baselines
├── correctness/
│   ├── __init__.py
│   ├── test_pricing_correctness.py
│   ├── test_indicators_correctness.py
│   ├── test_scoring_correctness.py
│   └── test_orchestration_correctness.py
├── stability/
│   ├── __init__.py
│   ├── test_pricing_stability.py
│   ├── test_indicators_stability.py
│   ├── test_scoring_stability.py
│   └── test_orchestration_stability.py
└── performance/
    ├── __init__.py
    └── test_benchmarks.py

tools/
├── generate_quantlib_baselines.py   # QuantLib baseline generator (dev-only)
└── math_audit_report.py             # Markdown report from pytest JSON output

src/options_arena/
├── models/
│   ├── enums.py                     # + AuditSeverity, AuditLayer
│   ├── audit.py                     # NEW: AuditFinding, AuditReport, AuditLayerSummary
│   └── __init__.py                  # + re-exports
└── cli/
    ├── audit.py                     # NEW: audit_app Typer group
    └── app.py                       # + register audit_app
```

### Implementation Approach

1. **Models first**: Define AuditSeverity/AuditLayer enums + AuditFinding/AuditReport/AuditLayerSummary models
2. **Reference data**: Compile academic known-values JSON from Hull/BAW papers; build QuantLib baseline generator
3. **Correctness tests**: Parametrized tests comparing each function against reference data
4. **Stability tests**: Hypothesis strategies per function + predefined extreme input battery + NaN/Inf injection
5. **Performance tests**: pytest-benchmark with representative inputs (ATM, 30 DTE, σ=0.25)
6. **CLI command**: `options-arena audit math` orchestrates pytest runs and report generation
7. **Agent discovery**: `/math-audit` skill enhancement for quant-analyst agent

### Key Design Decisions

- **QuantLib is dev-only**: Baseline JSON is pre-generated and committed. Tests load JSON, not QuantLib.
- **Hypothesis profiles**: `ci` (100 examples, <30s), `thorough` (1000 examples, manual runs)
- **Coverage meta-test**: AST-based scanning of source modules to discover mathematical functions, then asserts each has tests in all 3 layers
- **Agent discovery is non-blocking**: Not a CI gate — findings require human review before becoming tests

## Test Strategy Preview

### Existing Patterns to Follow
- **Pricing tests**: `tests/unit/pricing/` — 6 files, 32 test classes, parametrized over S/K/T/r/q/σ grids
- **Indicator tests**: `tests/unit/indicators/` — 18 files covering all indicator categories, includes extended tests and bugfix regressions
- **Scoring tests**: `tests/unit/scoring/` — 13 files covering composite, contracts, direction, normalization
- **Agent tests**: `tests/unit/agents/` — Uses `pydantic_ai.models.test.TestModel`, `ALLOW_MODEL_REQUESTS = False`

### New Marker Registration
```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    # ... existing markers ...
    "audit_correctness: mathematical correctness vs academic + QuantLib references",
    "audit_stability: numerical stability with Hypothesis + extreme inputs + NaN injection",
    "audit_performance: performance benchmarks with regression detection",
]
```

### New Dev Dependencies
```bash
uv add --dev hypothesis        # Property-based testing
uv add --dev pytest-benchmark  # Performance regression detection
# QuantLib: evaluate Windows/Python 3.13 compatibility first
```

## Estimated Complexity

**L (Large)** — Justification:
- 87 mathematical functions × 3 audit layers = 261+ test cases minimum
- Reference data compilation requires academic paper review + QuantLib baseline generation
- Hypothesis strategies need domain-specific input generators per function category
- CLI command, report generator, and coverage meta-test are substantial infrastructure
- However: all source modules are read-only (no risky refactoring), patterns are well-established in the codebase, and the 4 epics in the PRD can run partially in parallel

**Estimated: 12-16 GitHub issues across 4 epics** (per PRD phasing)
