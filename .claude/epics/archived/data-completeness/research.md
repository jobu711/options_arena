# Research: data-completeness

## PRD Summary

Three data gaps to fill:
1. **Active-contract P&L** — `OutcomeCollector` lacks `OptionsDataService` injection, so non-expired contracts always have `None` for `exit_contract_mid`, `contract_return_pct`, and `is_winner`. Only expired contracts compute returns.
2. **Short interest data** — yfinance provides `shortRatio` and `shortPercentOfFloat` but `TickerInfo` has no fields for them. The Fundamental agent's `short_interest_analysis` field is always null.
3. **Indicator signal interpretation** — TickerDrawer renders raw percentile numbers with no labels. Users must memorize thresholds (RSI >70 = overbought, ADX >25 = strong trend, etc.).

## Relevant Existing Modules

- `services/outcome_collector.py` — Core target for Feature 1. Constructor accepts `(config, repo, market_data)`. Lines 237-260 have explicit TODO comment: "Option chain data would require OptionsDataService (not injected here)."
- `services/options_data.py` — `OptionsDataService` with `fetch_chain(ticker, expiration) -> list[OptionContract]`. Already on `app.state.options_data`.
- `services/market_data.py` — `fetch_ticker_info()` (lines 395-466) uses `safe_float(info.get("fieldName"))` pattern. Short interest fields absent.
- `models/market_data.py` — `TickerInfo` (frozen=True) has 15 fields, no short interest.
- `models/analysis.py` — `MarketContext` has ~60 fields, no short_ratio.
- `models/analytics.py` — `ContractOutcome` already has `exit_contract_mid`, `contract_return_pct`, `is_winner` fields (all `None` for active contracts).
- `agents/_parsing.py` — `render_context_block()` builds text context. Has `## Fundamental Profile` section. Uses `_render_optional()` helper.
- `agents/orchestrator.py` — `build_market_context()` (lines 101-174) reads from `TickerInfo`.
- `indicators/fundamental.py` — `compute_short_interest(short_ratio)` function already exists (lines 74-94), validates finite + non-negative.
- `api/deps.py` — `get_outcome_collector()` creates `OutcomeCollector` without `options_data`. `OptionsDataService` already imported (line 19).
- `cli/outcomes.py` — Two `OutcomeCollector` instantiation sites (lines 73, 185), neither creates `OptionsDataService`.
- `web/src/components/TickerDrawer.vue` — Indicator grid at lines 291-302. Uses `formatSignalName()` and `formatSignalValue()`. No `classifySignal` exists anywhere.
- `web/src/components/DirectionBadge.vue` — Colored badge pattern (green/red/yellow spans). PrimeVue `Tag` already imported in TickerDrawer.

## Existing Patterns to Reuse

- **safe_float extraction** (`market_data.py`): `safe_float(info.get("shortRatio"))` — rejects NaN/Inf, returns `float | None`.
- **field_validator NaN defense** (`models/`): `math.isfinite(v) and v >= 0` on all numeric optional fields.
- **_render_optional** (`_parsing.py`): `_render_optional("SHORT RATIO", ctx.short_ratio, ".2f")` for context block.
- **Constructor DI** (`outcome_collector.py`): Add `options_data: OptionsDataService | None = None` as optional param.
- **PrimeVue Tag** (`TickerDrawer.vue`): Already imported at line 9. `severity` prop maps to `success`/`danger`/`warn`/`info`.
- **Service close pattern** (CLI): `finally` block closes services. Must add `options_data.close()`.
- **asyncio.wait_for** (services): Standard pattern for external calls with timeout.

## Existing Code to Extend

| File | What Exists | What Changes |
|------|------------|-------------|
| `services/outcome_collector.py` | Constructor takes 3 params. `_process_active_contract()` sets all option fields to None. | Add `options_data: OptionsDataService | None = None` 4th param. In `_process_active_contract()`, call `fetch_chain()` → match strike+type → compute mid/return. |
| `api/deps.py:75-81` | `get_outcome_collector()` passes 3 args. | Add `options_data=request.app.state.options_data`. |
| `cli/outcomes.py:73,185` | Creates `MarketDataService` + `OutcomeCollector`. | Create `OptionsDataService`, pass to collector, close in `finally`. |
| `models/market_data.py` | `TickerInfo` has 15 fields, frozen=True. | Add `short_ratio: float | None = None`, `short_pct_of_float: float | None = None` with validators. |
| `services/market_data.py:436-456` | `TickerInfo(...)` constructor call. | Add `short_ratio=safe_float(info.get("shortRatio"))`, `short_pct_of_float=safe_float(info.get("shortPercentOfFloat"))`. |
| `models/analysis.py` | `MarketContext` flat model, ~60 fields. | Add `short_ratio: float | None = None`. |
| `agents/orchestrator.py:172` | `MarketContext(...)` constructor. | Add `short_ratio=ticker_info.short_ratio`. |
| `agents/_parsing.py:443-457` | Fundamental Profile section. | Add `_render_optional("SHORT RATIO", ctx.short_ratio, ".2f")`. |
| `web/src/components/TickerDrawer.vue:291-302` | Signal grid: name + value. | Add `classifySignal()` function + `<Tag>` for interpretation labels. Expand CSS grid to 3 columns. |

## Potential Conflicts

- **Cache staleness** — `TickerInfo` is cached with key `yf:fundamentals:{ticker}:info`. Adding fields without busting cache means old cached responses won't have short interest. **Mitigation**: Bump cache key to `:v2` or clear on first run. Alternatively, `safe_float()` returns `None` for missing fields, so old cached data just shows `None` — acceptable since cache TTL is market-hours-aware.
- **Frozen model construction** — `TickerInfo` is `frozen=True`. New fields with defaults (`None`) are backward compatible with existing constructor calls. No conflict.
- **MarketContext persistence** — `MarketContext` is persisted to SQLite. Adding a new `float | None` field requires the column in the DB. Check if `market_context` table schema is dynamic or fixed. **Mitigation**: If fixed schema, add migration. If JSON blob, no issue.
- **Test fixtures** — 27+ test files reference `MarketContext`. Adding a new field with `None` default won't break existing fixtures. `TickerInfo` fixtures in ~6 test files also safe with default `None`.

## Open Questions

1. **MarketContext persistence schema** — Is `short_ratio` stored as a column or part of a JSON blob? May need a SQL migration.
2. **Cache key versioning** — Should we bump the `TickerInfo` cache key to avoid stale hits, or accept `None` for cached entries until they expire?
3. **short_pct_of_float range validation** — yfinance returns this as a decimal fraction (0.05 = 5%). Should we validate `<= 1.0` or allow higher values (some short squeezes exceed 100% of float)?
4. **OutcomeCollectionMethod enum** — Should active contracts with option chain data use a new enum value (e.g., `OPTION_CHAIN`) or reuse `MARKET`?

## Recommended Architecture

### Feature 1: Active-Contract P&L (OptionsDataService DI)
- Add `options_data: OptionsDataService | None = None` to `OutcomeCollector.__init__()`
- In `_process_active_contract()`: if `self._options_data is not None`, wrap `fetch_chain()` in `asyncio.wait_for(timeout=10)`, find matching contract by `strike == contract.strike and option_type == contract.option_type`, compute `exit_contract_mid = (bid + ask) / Decimal("2")`
- All three instantiation sites (deps.py, 2x cli/outcomes.py) updated
- Graceful fallback: `try/except Exception` → log warning, return `None` (current behavior)

### Feature 2: Short Interest Fields
- Add 2 fields to `TickerInfo` with `field_validator` (isfinite + non-negative)
- Extract via `safe_float()` in `fetch_ticker_info()`
- Thread `short_ratio` to `MarketContext` → `render_context_block()` Fundamental Profile section
- `compute_short_interest()` in indicators already exists — no new indicator logic needed

### Feature 3: Indicator Signal Interpretation
- New `classifySignal(key: string, value: number): { label: string; severity: string } | null` in TickerDrawer or a shared utility
- 6 indicators with thresholds per PRD (rsi, stochastic_rsi, adx, sma_alignment, relative_volume, bb_width)
- Render as PrimeVue `<Tag>` alongside existing value
- Expand signal-grid CSS to accommodate third column

### Implementation Waves
| Wave | Tasks | Parallel? |
|------|-------|-----------|
| 1a | Short interest: TickerInfo fields + fetch_ticker_info extraction + validators | Yes |
| 1b | Signal interpretation: classifySignal utility + TickerDrawer update | Yes (independent) |
| 2a | Short interest threading: MarketContext field + orchestrator + _parsing.py | After 1a |
| 2b | OptionsDataService DI: OutcomeCollector + deps.py + CLI | Independent of 1a |
| 3 | Tests for all three features | After 2a+2b |

## Test Strategy Preview

### Existing Test Patterns
- **OutcomeCollector** (23 tests): Constructor injection with `AsyncMock` for each dep. `_market_today()` patched.
- **MarketDataService** (41 tests): `_yf_call` patched. `safe_float` validated in model tests.
- **TickerInfo** (31 model tests): Direct construction. NaN/Inf validators tested.
- **MarketContext** (27 referencing files): Shared `conftest.py` fixture.
- **E2E**: 5 TickerDrawer tests across 2 suites. Mock pattern: `page.route()` interceptors.

### New Tests Needed
| Feature | Test File | Tests |
|---------|-----------|-------|
| Active P&L | `test_outcome_collector.py` | fetch_chain success → mid computed, fetch_chain failure → None fallback, no OptionsDataService → None (backward compat), matching strike/type logic, timeout handling |
| Short interest | `test_market_data.py` (model) | valid short_ratio, None passthrough, NaN rejected, negative rejected, Inf rejected |
| Short interest | `test_market_data.py` (service) | yfinance info has shortRatio → extracted, info missing → None |
| Short interest | `test_analysis.py` | MarketContext with short_ratio, render_context_block includes SHORT RATIO |
| Signal labels | E2E or manual | Indicators show colored tags for RSI/ADX/BB Width |

### Mocking Strategies
- `OptionsDataService` in OutcomeCollector tests: `AsyncMock` with `fetch_chain` returning `[OptionContract(...)]`
- yfinance short interest: patch `_yf_call` to return info dict with `shortRatio`/`shortPercentOfFloat`
- TickerDrawer E2E: mock `/api/scan/{id}/scores` with signal values in threshold ranges

## Estimated Complexity

**Medium (M)** — 8-9 Python files, 1 Vue component, ~15-20 new tests. No new models or services. All changes extend existing code with established patterns. The OptionsDataService DI is the most complex piece (async chain fetch + matching logic + error handling), but the pattern is well-established. Short interest is straightforward field addition. Signal interpretation is pure frontend display logic.
