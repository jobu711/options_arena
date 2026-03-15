# Research: multi-leg-strategies

## PRD Summary

Add a multi-leg option strategy builder to Options Arena. The pipeline currently recommends a single contract per ticker. This feature adds strategy construction (vertical spreads, iron condors, straddles, strangles), P&L mechanics, Greeks aggregation, and an IV-regime-based selection engine. Integrates into the scan pipeline, debate agents, and web UI. Zero new dependencies — all implemented with existing numpy/scipy/Decimal stack.

## Relevant Existing Modules

- `models/options.py` — `SpreadLeg`, `OptionSpread` already defined (frozen, validated). `OptionGreeks` has first + second-order Greeks. All re-exported from `models/__init__.py`.
- `models/enums.py` — `SpreadType` (6 variants: VERTICAL, CALENDAR, IRON_CONDOR, STRADDLE, STRANGLE, BUTTERFLY), `PositionSide` (LONG, SHORT), `VolRegime`, `MarketRegime` all exist.
- `models/analysis.py` — `TradeThesis.recommended_strategy: SpreadType | None = None` exists but is always `None` in code paths (only set by LLM). `VolatilityThesis` also has this field. `RecommendedContract` is single-leg persistence model.
- `scoring/contracts.py` — Full single-leg pipeline: `filter_contracts()` → `select_expiration()` → `compute_greeks()` → `select_by_delta()` → `recommend_contracts()`. Returns 0 or 1 contracts.
- `pricing/dispatch.py` — `option_greeks()`, `option_price()`, `option_iv()` dispatch to BSM/BAW. Sole public interface for pricing math.
- `indicators/iv_analytics.py` — `classify_vol_regime(iv_rank)` maps to `VolRegime` enum (LOW <25, NORMAL 25-50, ELEVATED 50-75, EXTREME >=75). Direct input for strategy selection.
- `scan/phase_options.py` — `process_ticker_options()` calls `_recommend()` at line ~640. `all_contracts` and `ticker_score.signals.iv_rank` are in scope. This is the hook point.
- `scan/phase_persist.py` — Persists `RecommendedContract` per ticker. Would need parallel persistence for spreads.
- `agents/orchestrator.py` — `run_debate()` receives contracts + MarketContext. `DebateDeps` dataclass carries all agent inputs. `recommended_strategy` flows from VolatilityThesis → TradeThesis.
- `api/routes/debate.py` — `GET /api/debate/{id}` returns `DebateResultDetail` including `thesis.recommended_strategy` as string.

## Existing Patterns to Reuse

- **Contract factory** (`tests/factories.py`): `make_option_contract(**kw)` with full defaults. Used by all scoring tests. Extend for spread leg construction.
- **`scoring/contracts.py` pipeline**: The `filter_contracts()` → `compute_greeks()` → `select_by_delta()` chain provides all inputs the strategy builder needs. Reuse `filter_contracts()` to get candidate pools for short legs.
- **`classify_vol_regime(iv_rank)`**: Already maps IV rank to LOW/NORMAL/ELEVATED/EXTREME. Directly usable as the IV regime input for strategy selection without re-implementing.
- **`_render_optional()` pattern** in agent context rendering: Guards `None` + `math.isfinite()` before formatting. Use this pattern for spread fields added to `MarketContext`.
- **`DebateDeps` dataclass extension**: Add `spread_analysis: SpreadAnalysis | None = None` following the existing optional field pattern (same as `dimensional_scores`, `flow_output`, etc.).
- **Frozen model + computed fields**: `OptionContract.mid`, `.spread`, `.dte` pattern. Apply to `SpreadAnalysis` for derived metrics.
- **`field_serializer` for Decimal**: Every model with Decimal fields uses `serialize_decimal`. Required on `SpreadAnalysis`.
- **Migration pattern**: Sequential numbering (`033_*.sql`), `ALTER TABLE` for additions. Latest is `032_second_order_greeks.sql`.
- **Repository mixin pattern**: New spread persistence methods go in a new mixin or extend `ScanMixin`.

## Existing Code to Extend

- `src/options_arena/models/options.py` — Add `SpreadAnalysis` model alongside existing `SpreadLeg`/`OptionSpread`
- `src/options_arena/scan/phase_options.py` — Hook `select_strategy()` after `_recommend()` in `process_ticker_options()`
- `src/options_arena/scan/models.py` — Add `spread_analyses: dict[str, SpreadAnalysis]` to `OptionsResult`
- `src/options_arena/scan/phase_persist.py` — Persist spread alongside `RecommendedContract`
- `src/options_arena/agents/orchestrator.py` — Pass `SpreadAnalysis` to agents via `DebateDeps`; surface in `MarketContext`
- `src/options_arena/models/analysis.py` — Add spread-related flat fields to `MarketContext` for agent rendering
- `src/options_arena/agents/prompts/volatility.py` — Enrich prompt with actual spread data (currently LLM guesses strategy)
- `src/options_arena/agents/prompts/risk.py` — Enrich prompt with max_loss, risk/reward, PoP from `SpreadAnalysis`
- `src/options_arena/api/schemas.py` — Add spread fields to `DebateResultDetail` / `TickerDetail`
- `src/options_arena/cli/rendering.py` — Extend thesis rendering with spread leg table
- `src/options_arena/reporting/debate_export.py` — Include spread details in markdown/PDF export

## New Files to Create

- `src/options_arena/pricing/spreads.py` — `aggregate_spread_greeks(legs) -> OptionGreeks`. Pure math, imports `models/` only.
- `src/options_arena/scoring/spreads.py` — `build_vertical_spread()`, `build_iron_condor()`, `build_straddle()`, `build_strangle()`, `select_strategy()`. Imports `models/` and `pricing/dispatch` only.
- `data/migrations/033_spread_recommendations.sql` — Tables for persisting spread legs
- `tests/unit/pricing/test_spreads.py` — Greeks aggregation tests
- `tests/unit/scoring/test_spreads.py` — Strategy construction + selection tests

## Potential Conflicts

- **`OptionsResult` shape change**: Adding `spread_analyses` to `OptionsResult` requires updating `phase_persist.py` and any code that destructures the result. Contained within `scan/` — no cross-module breakage.
- **`MarketContext` field expansion**: Adding flat spread fields (`spread_net_premium`, `spread_max_profit`, etc.) increases the context block sent to agents. Must be guarded by `_render_optional()` to avoid bloating prompts when no spread is built.
- **`RecommendedContract` is single-leg**: Spread persistence requires a new table (`spread_recommendations` with FK to `recommended_contracts` legs). Cannot reuse the existing `recommended_contracts` table directly for multi-leg.
- **LLM vs algorithmic `recommended_strategy`**: Currently the Volatility Agent LLM picks the strategy type. The new algorithmic engine will also pick. Need a clear precedence rule — algorithmic should take priority since it has actual construction behind it.
- **Test count growth**: PRD estimates ~65 new tests. Current suite is 4,522. Manageable, but strategy construction tests with Decimal arithmetic need careful fixture setup.

## Resolved Design Decisions

1. **Strategy persistence**: Yes — persist spread recommendations to SQLite via migration 033. Enables outcome tracking and backtesting of spread recommendations, matching the single-leg `RecommendedContract` pattern.
2. **LLM vs algorithmic precedence**: Algorithmic engine wins. It has actual constructed legs with verified P&L. The LLM's `VolatilityThesis.recommended_strategy` becomes a secondary agreement/disagreement signal, not the displayed recommendation.
3. **Spread width configuration**: New `SpreadConfig(BaseModel)` nested under `AppSettings`. Fields: vertical strike width, iron condor wing width, short-leg delta targets, etc. Follows `PricingConfig`/`ScanConfig` pattern. Env-overridable via `ARENA_SPREAD__*`.
4. **NEUTRAL direction handling**: Already resolved by existing code. `filter_contracts()` passes both calls and puts when direction is NEUTRAL — exactly what iron condors and strangles need. No changes required.

## Recommended Architecture

### Data Flow

```
Phase 3 (phase_options.py)
  └─ _recommend() → single OptionContract (existing)
  └─ select_strategy() [NEW] → SpreadAnalysis | None
       ├─ classify_vol_regime(iv_rank) → VolRegime
       ├─ direction + confidence → strategy type decision
       ├─ build_vertical_spread() / build_iron_condor() / build_straddle() / build_strangle()
       │    └─ filter_contracts() to get candidate legs from all_contracts
       │    └─ aggregate_spread_greeks() from pricing/spreads.py
       │    └─ compute P&L, breakevens, PoP
       └─ return SpreadAnalysis (spread + analytics) or None

Phase 4 (phase_persist.py)
  └─ persist SpreadAnalysis alongside RecommendedContract

Debate (orchestrator.py)
  └─ SpreadAnalysis passed via DebateDeps
  └─ Flat spread fields added to MarketContext
  └─ Agents see actual spread data (not just LLM guess)
```

### Module Boundaries (Verified)

- `pricing/spreads.py` → imports `models/` only. Pure Greeks aggregation.
- `scoring/spreads.py` → imports `models/` + `pricing/dispatch` only. Strategy construction + selection.
- `scan/phase_options.py` → calls `scoring/spreads.py` (never `pricing/` directly).
- `agents/` → receives `SpreadAnalysis` pre-computed. No pricing/scoring imports.

### Key Design Decisions

- `SpreadAnalysis` goes in `models/options.py` (near `OptionSpread`/`SpreadLeg`).
- Construction functions return `SpreadAnalysis | None` — `None` = graceful fallback to single contract.
- All monetary values (`net_premium`, `max_profit`, `max_loss`, `breakevens`) are `Decimal`.
- Greeks aggregation returns `OptionGreeks` (same model as single-contract Greeks).
- IV regime thresholds come from config, not hardcoded.
- PoP uses BSM `N(d2)` via `scipy.stats.norm.cdf` — already in the dependency stack.

## Test Strategy Preview

- **Existing patterns**: `tests/factories.py::make_option_contract()` for building legs. `tests/unit/scoring/conftest.py` for `IndicatorSignals` fixtures.
- **New test files**: `tests/unit/pricing/test_spreads.py` (~15 tests for Greeks aggregation), `tests/unit/scoring/test_spreads.py` (~25 tests for construction + ~10 for selection engine).
- **Key test scenarios**: Bull call spread P&L formulas, bear put spread, iron condor 4-leg construction, straddle/strangle breakevens, `None` returns on insufficient contracts, Greeks sign correctness (short leg negates), PoP bounds [0, 1], Decimal precision survival.
- **Edge cases**: Single contract available (can't build spread → None), zero-width strike (same strike both legs → None), missing Greeks on a leg → None, iv_rank is None → single contract fallback.

## Estimated Complexity

**L (Large)** — 5 delivery issues across 2 new files + 11 modified files + ~65 new tests. The construction logic is straightforward arithmetic, but integration touches many layers (models, scoring, pricing, scan pipeline, agents, API, CLI, reporting). The database migration and persistence layer add complexity. No new dependencies mitigates risk.

Justification: Similar in scope to the native-quant epic (also L), which added `analysis/` module + second-order Greeks + migration 032 + API enrichment. This epic adds fewer new concepts but more integration points.
