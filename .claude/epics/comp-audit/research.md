# Research: comp-audit

## PRD Summary

Integrate 7 cherry-picked ideas from ai-hedge-fund competitive audit into Options Arena:
1. **Hurst Exponent** — regime classification indicator (trending vs mean-reverting)
2. **Risk-Adjusted Metrics** — Sharpe, Sortino, max drawdown with date tracking
3. **Agent Personas** — distinctive professional identities for 6 debate agents
4. **Constraint Pre-Checks** — deterministic validation before agent invocation
5. **Position Sizing** — vol-regime-based allocation recommendations
6. **Multi-Methodology Valuation** — 4-model composite fair value (DCF, EV/EBITDA, residual income)
7. **Portfolio Correlation** — pairwise Pearson correlation matrix for watchlist tickers

Delivered in 3 waves: Wave 1 (independent), Wave 2 (analysis core), Wave 3 (data-heavy).

## Relevant Existing Modules

- `indicators/` — Hurst goes here as `hurst.py`. Pattern: `hv_estimators.py` (pandas in, float|None out, no Pydantic models, NaN defense, `InsufficientDataError`). Currently 13 files, 18 functions.
- `analysis/` — **Package exists but has no Python files** (only CLAUDE.md, which is mislabeled — describes scoring/ rules). All of performance.py, position_sizing.py, valuation.py, correlation.py are NEW. Architecture boundary: can import `models/`, `pricing/dispatch`, `scipy`; cannot import services/indicators/scan.
- `models/` — Central models: `MarketContext` (100+ fields, 16 existing `fd_*` fields), `IndicatorSignals` (68 fields), `OptionsFilters` (constraint thresholds). New models span `analytics.py`, `analysis.py`, `enums.py`, `config.py`, plus new `valuation.py` and `correlation.py`.
- `scoring/` — `composite.py` has `INDICATOR_WEIGHTS` (22 entries) with import-time sum==1.0 guard. `normalization.py` has `DOMAIN_BOUNDS` (23 entries) and `INVERTED_INDICATORS` frozenset.
- `agents/prompts/` — 6 prompt files to modify. Pattern: string constant = body + `PROMPT_RULES_APPENDIX`. `# VERSION:` comment required.
- `agents/` — `orchestrator.py` (build_market_context, run_debate), `_parsing.py` (DebateDeps dataclass, render_context_block). Both modified by FR-C4 + FR-C5.
- `data/_analytics.py` — `AnalyticsMixin` with existing equity curve/drawdown queries. `contract_outcomes` table has `contract_return_pct`, `holding_days`, `exit_date` — sufficient for Sharpe/Sortino.
- `api/routes/analytics.py` — 14 existing endpoints on `/api/analytics`. Router already registered. 2 new endpoints needed.
- `cli/outcomes.py` — 8 existing subcommands. Pattern: sync Typer command wraps `asyncio.run()`. 2 new subcommands needed.

## Existing Patterns to Reuse

- **Indicator pattern** (`hv_estimators.py`): `float | None` return, `math.isfinite()` guard, `None` on insufficient data, cited references in docstring, `.to_numpy()` for computation.
- **Model snapshot pattern**: `ConfigDict(frozen=True)`, `field_validator` with `isfinite()` before range checks, UTC validator on datetime fields.
- **Weight integration pattern** (`composite.py`): add entry to `INDICATOR_WEIGHTS` + `DOMAIN_BOUNDS` + `__init__.py` re-export. Import-time guard enforces sum==1.0.
- **AnalyticsMixin query pattern**: SQL query → row mapping → typed model return. `Decimal` from TEXT, enum from string, datetime via `fromisoformat`. `pytest.approx()` for float comparisons.
- **CLI subcommand pattern**: `@outcomes_app.command("name")` sync def → `asyncio.run(_async)`. Full service lifecycle. `isfinite()` before Rich table formatting.
- **API endpoint pattern**: `@router.get("/path")` with `Depends(get_repo)`, `Query()` params, return Pydantic model directly.
- **DebateDeps extension pattern**: add optional field with `None` default to `@dataclass`. Render in `render_context_block()`.
- **MarketContext field addition**: add `float | None` field, add name to `validate_optional_finite` field list, add to appropriate ratio method.

## Existing Code to Extend

- `src/options_arena/models/analysis.py` — `MarketContext`: add 6 new `fd_*` fields, 3 valuation fields, 2 position sizing fields. Must update `validate_optional_finite` validator list and `financial_datasets_ratio()`.
- `src/options_arena/models/scan.py` — `IndicatorSignals`: add `hurst_exponent: float | None = None` (becomes 69th field).
- `src/options_arena/models/analytics.py` — add `RiskAdjustedMetrics` model alongside existing `EquityCurvePoint`, `DrawdownPoint`.
- `src/options_arena/models/enums.py` — add 3 new StrEnums (29 existing → 32).
- `src/options_arena/models/config.py` — add `PositionSizingConfig` to `AppSettings` (12th nested config).
- `src/options_arena/scoring/composite.py` — redistribute `roc` (0.03→0.02) and `put_call_ratio` (0.03→0.02), add `hurst_exponent` (0.02, "regime").
- `src/options_arena/scoring/normalization.py` — add `"hurst_exponent": (0.0, 1.0)` to `DOMAIN_BOUNDS`.
- `src/options_arena/agents/_parsing.py` — add `constraint_warnings` to `DebateDeps`, render position sizing + valuation + constraints in `render_context_block()`.
- `src/options_arena/agents/orchestrator.py` — call `check_contract_constraints()`, `compute_position_size()`, and `compute_composite_valuation()` in `build_market_context()`.
- `src/options_arena/data/_analytics.py` — add `get_risk_adjusted_metrics()` to `AnalyticsMixin`.
- `src/options_arena/api/routes/analytics.py` — add 2 new GET endpoints.
- `src/options_arena/cli/outcomes.py` — add 2 new subcommands.

## Potential Conflicts

1. **Weight sum guard (critical)** — `INDICATOR_WEIGHTS` has import-time assertion. The `roc` and `put_call_ratio` reductions + `hurst_exponent` addition must be atomic in one edit. Arithmetic: -0.01 -0.01 +0.02 = net 0.
2. **MarketContext validator list** — The `validate_optional_finite` decorator lists ~60 field names. Every new `float | None` field must be added. Forgetting = silent NaN/Inf acceptance.
3. **DebateDeps dual modification** — FR-C4 (constraint_warnings) and FR-C5 (position sizing context) both modify `DebateDeps` and `render_context_block()`. Wave 2 puts them in separate issues — coordinate carefully.
4. **IndicatorSignals field count** — Docstring says "68 named indicator fields." Adding hurst makes 69. Any field-count test will fail if not updated.
5. **`analysis/` package creation** — Directory exists but has no `__init__.py`. Must be created before any import works. Wave 1 Issue 2 creates it.
6. **FD data dependency** — FR-C6 valuation requires 6 new `fd_*` fields that depend on FinancialDatasets epic #393. Valuation must gracefully return None when FD fields are absent.
7. **`analysis/CLAUDE.md` is mislabeled** — Current content describes scoring/ rules. Should be rewritten for analysis/ constraints before implementation.
8. **`RiskAssessment.recommended_position_size`** — Existing `str | None` field on RiskAssessment. FR-C5 adds structured fields to `MarketContext` separately; does NOT touch RiskAssessment. No conflict, but worth noting.

## Open Questions

1. **FR-C6 data availability** — The 6 new `fd_*` fields require FinancialDatasets epic #393 to populate them. Should FR-C6 add the model fields now (accepting None) and implement computation, with population deferred to #393?
2. **analysis/ CLAUDE.md** — Should we rewrite it for the analysis module's actual constraints before starting implementation?
3. **Hurst pipeline integration** — Where exactly in Phase 2 does hurst get computed? Via the existing `_compute_indicators()` call path in `phase_scoring.py`?
4. **Correlation data source** — FR-C7 needs OHLCV for watchlist tickers. Should this call `market_data.fetch_daily_prices()` from the API/CLI layer, or should correlation computation be a standalone service?

## Recommended Architecture

### New Package: `analysis/`
Create `src/options_arena/analysis/` with:
- `__init__.py` — re-exports all public functions
- `performance.py` — `compute_risk_adjusted_metrics()` → `RiskAdjustedMetrics`
- `position_sizing.py` — `compute_position_size()` → `PositionSizeResult`
- `valuation.py` — `compute_composite_valuation()` → `CompositeValuation`
- `correlation.py` — `compute_correlation_matrix()` → `CorrelationMatrix`

All functions: typed inputs (Pydantic models + primitives), typed output (Pydantic models), no I/O, no API calls.

### New Models
- `models/valuation.py` — `ValuationModelResult`, `CompositeValuation`
- `models/correlation.py` — `PairwiseCorrelation`, `CorrelationMatrix`
- Extensions to existing: `analytics.py` (RiskAdjustedMetrics), `analysis.py` (ContractConstraint + MarketContext fields), `enums.py` (3 new StrEnums), `config.py` (PositionSizingConfig)

### Integration Points
- **Hurst → Scoring**: `indicators/hurst.py` → `IndicatorSignals.hurst_exponent` → `composite.py` weight
- **Constraints → Agents**: `agents/constraints.py` → `DebateDeps.constraint_warnings` → prompt injection
- **Position Sizing → Agents**: `analysis/position_sizing.py` → `MarketContext` fields → `render_context_block()`
- **Valuation → Agents**: `analysis/valuation.py` → `MarketContext` fields → fundamental agent prompt
- **Performance → Data Layer**: `analysis/performance.py` ← `contract_outcomes` SQL → API/CLI
- **Correlation → API/CLI**: `analysis/correlation.py` ← OHLCV data → API/CLI endpoints

## Test Strategy Preview

### Existing Test Patterns
- **Indicators**: `tests/unit/indicators/test_hv_estimators.py` — synthetic pd.Series, known-value checks, insufficient data → None, NaN guard, flat prices
- **Models**: `tests/unit/models/` — valid construction, JSON roundtrip, frozen assertion, validator edge cases (NaN, Inf, out-of-range)
- **Data queries**: `tests/unit/data/test_analytics_queries.py` — `pytest.mark.db`, in-memory SQLite, `pytest_asyncio` fixtures, `pytest.approx()`
- **Scoring**: `tests/unit/scoring/test_composite.py`, `test_normalization.py` — weight sum verification, domain bounds, inverted indicators

### New Test Files (~85 tests across 10 files)
| File | Tests | Focus |
|------|-------|-------|
| `tests/unit/indicators/test_hurst.py` | ~10 | Known Hurst values, edge cases, R^2 filter |
| `tests/unit/analysis/test_performance.py` | ~10 | Sharpe/Sortino formulas, min trade threshold |
| `tests/unit/agents/test_personas.py` | ~6 | Persona text present in prompts, version bumps |
| `tests/unit/agents/test_constraints.py` | ~12 | Each violation type, mixed hard/soft, empty list |
| `tests/unit/analysis/test_position_sizing.py` | ~12 | Each vol tier, interpolation, correlation penalty |
| `tests/unit/analysis/test_valuation.py` | ~20 | Each model independently, combiner, all-None |
| `tests/unit/analysis/test_correlation.py` | ~15 | Pairwise computation, min overlap, NaN handling |
| `tests/unit/models/test_new_models.py` | ~10 | Frozen, validators, enums, roundtrip |
| `tests/unit/scoring/test_hurst_integration.py` | ~5 | Weight sum, domain bounds, normalization |
| `tests/unit/data/test_risk_metrics_query.py` | ~5 | SQL query, empty outcomes, edge cases |

## Estimated Complexity

**XL** — 9 new files, 31 modified files, ~85 new tests, 3 delivery waves spanning indicators, analysis, models, scoring, agents, data, API, and CLI layers. Touches every major module except `services/` and `scan/` (other than the hurst pipeline hook). The valuation feature (FR-C6) alone has 6 modified files and depends on FD data availability. The weight redistribution and MarketContext validator list are precision-critical.
