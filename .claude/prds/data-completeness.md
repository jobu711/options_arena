---
name: data-completeness
description: Active-contract P&L via OptionsDataService DI, short interest from yfinance, and indicator signal interpretation in TickerDrawer
status: planned
created: 2026-03-06T17:18:19Z
---

# PRD: data-completeness

## Executive Summary

Three data gaps that weaken the tool's analytical output: (1) active (non-expired) contracts always show `None` for P&L because `OutcomeCollector` lacks `OptionsDataService` injection — only expired contracts compute returns, (2) short interest data (`shortRatio`, `shortPercentOfFloat`) is available in yfinance but never extracted into `TickerInfo`, and (3) indicator values in the TickerDrawer show raw percentile numbers without interpretation (e.g., "RSI: 73.45" with no "Overbought" label or color). This PRD fills all three gaps.

## Problem Statement

### What problem are we solving?

1. **Active-contract P&L (F7)** — `OutcomeCollector._process_active_contract()` at `outcome_collector.py:240` explicitly sets `exit_contract_mid = None` with a comment: "Option chain data would require OptionsDataService (not injected here)." The constructor only accepts `MarketDataService`. For non-expired contracts, `contract_return_pct` and `is_winner` are always `None`. Analytics endpoints (score-calibration, delta-performance) only have data from expired contracts, making results sparse for weeks after a scan.

2. **Short interest missing (F8)** — yfinance `Ticker.info` provides `shortRatio` and `shortPercentOfFloat`. The `fetch_ticker_info()` method already reads ~15 fields from `info` but skips short interest. The Fundamental agent prompt explicitly handles "short_interest_analysis" (returns null when missing), and `indicators/fundamental.py` has a `short_interest()` function. But the source data is never fetched. `TickerInfo` has no `short_ratio` or `short_pct_of_float` fields.

3. **Indicator signals have no interpretation (F11)** — `TickerDrawer.vue:227-239` renders indicators as a flat grid of name/value pairs. "RSI: 73.45" provides no guidance. Users must know that RSI >70 = overbought, ADX >25 = strong trend, BB Width expanding = volatility increasing. Color-coded interpretation labels (bullish/bearish/neutral) would make the data immediately actionable.

### Why is this important now?

- Analytics page (v2.9) will display score-calibration and delta-performance charts — active-contract P&L is needed for data density
- Short interest is a key factor for squeeze analysis and the Fundamental agent cites it
- Indicator interpretation is low-effort UX polish that makes the TickerDrawer useful to non-expert users

## User Stories

### US-1: Active Contract P&L
**As a** user viewing analytics charts,
**I want** P&L computed for active (non-expired) contracts using live option prices,
**So that** analytics data is available within days of a scan, not only after expiration.

**Acceptance Criteria:**
- `OutcomeCollector` accepts `OptionsDataService` in constructor
- For active contracts, fetches option chain for the contract's expiration
- Computes `exit_contract_mid` from bid/ask of matching strike/type
- `contract_return_pct` and `is_winner` populated for active contracts
- If option chain fetch fails, falls back to stock return only (current behavior)
- `api/deps.py` updated to inject `OptionsDataService`
- CLI `outcomes collect` updated to pass `OptionsDataService`

### US-2: Short Interest Data
**As a** user analyzing a ticker's squeeze potential,
**I want** short interest metrics visible in the data pipeline,
**So that** the Fundamental agent and scan scoring can use real short interest data.

**Acceptance Criteria:**
- `TickerInfo` gains `short_ratio: float | None = None` and `short_pct_of_float: float | None = None`
- `fetch_ticker_info()` extracts from yfinance `info["shortRatio"]` and `info["shortPercentOfFloat"]`
- Values validated as finite and non-negative
- `FundamentalSnapshot` (if exists) or `MarketContext` threads short interest to agents
- No crash if yfinance returns None for these fields

### US-3: Indicator Signal Interpretation
**As a** user viewing indicators in the TickerDrawer,
**I want** each indicator labeled with a bullish/bearish/neutral interpretation and color-coded,
**So that** I can instantly understand the signal without memorizing indicator thresholds.

**Acceptance Criteria:**
- RSI: <30 = "Oversold" (green), 30-70 = "Neutral" (yellow), >70 = "Overbought" (red)
- ADX: <15 = "Weak Trend", 15-25 = "Moderate", >25 = "Strong Trend"
- BB Width: <20 = "Compressed" (potential breakout), >80 = "Expanded" (high vol)
- SMA Alignment: >60 = "Bullish Alignment" (green), <40 = "Bearish" (red)
- Relative Volume: >70 = "High Volume" (notable), <30 = "Low Volume"
- Interpretation shown as colored badge next to the numeric value
- Thresholds apply to normalized 0-100 percentile values
- Indicators without clear interpretation thresholds show value only (no badge)

## Requirements

### Functional Requirements

#### FR-1: OptionsDataService Injection into OutcomeCollector
- Add `options_data: OptionsDataService | None = None` parameter to `OutcomeCollector.__init__()`
- In `_process_active_contract()`, if `options_data` is not None:
  1. Fetch option chain for contract's expiration via `options_data.fetch_chain()`
  2. Find matching contract by strike + option_type
  3. Compute `exit_contract_mid = (bid + ask) / 2`
  4. Compute `contract_return_pct` from entry/exit mid
  5. Set `is_winner = contract_return_pct > 0`
- If fetch fails or contract not found, fall back to `None` (current behavior)
- Wrap in `asyncio.wait_for()` with timeout

#### FR-2: DI Updates
- `api/deps.py`: Pass `request.app.state.options_data` to `OutcomeCollector()`
- CLI `outcomes` command: Create `OptionsDataService` and pass to collector
- Both injection points are optional — `OutcomeCollector` works without it (backward compatible)

#### FR-3: Short Interest Fields on TickerInfo
- Add to `TickerInfo` model in `models/market_data.py`:
  - `short_ratio: float | None = None`
  - `short_pct_of_float: float | None = None`
- Add `field_validator` for both: `math.isfinite(v)` and `v >= 0`
- Extract in `market_data.py:fetch_ticker_info()`:
  ```python
  short_ratio = safe_float(info.get("shortRatio"))
  short_pct_of_float = safe_float(info.get("shortPercentOfFloat"))
  ```

#### FR-4: Thread Short Interest to MarketContext
- Add `short_ratio: float | None = None` to `MarketContext`
- Populate from `TickerInfo` during `build_market_context()`
- Add to context block rendering in `_parsing.py` under Fundamental Profile section

#### FR-5: Indicator Interpretation Logic
- New TypeScript utility function `classifySignal(key: string, value: number): { label: string, severity: 'success' | 'danger' | 'warn' | 'info' }`
- Threshold table (for normalized 0-100 percentile values):

| Indicator | Green (Bullish) | Yellow (Neutral) | Red (Bearish) |
|-----------|----------------|------------------|---------------|
| rsi | <30 (Oversold) | 30-70 | >70 (Overbought) |
| stochastic_rsi | <20 (Oversold) | 20-80 | >80 (Overbought) |
| adx | >60 (Strong Trend) | 30-60 | <30 (Weak) |
| sma_alignment | >60 (Bullish) | 40-60 | <40 (Bearish) |
| relative_volume | >70 (High Vol) | 30-70 | <30 (Low Vol) |
| bb_width | <20 (Compressed) | 20-80 | >80 (Expanded) |

- Display as PrimeVue `Tag` component next to the numeric value

#### FR-6: TickerDrawer Signal Rendering Update
- Replace plain `<span>` for signal value with `<span> + <Tag>` pair
- Tag shows interpretation label with color
- Indicators not in the threshold table show value only (no tag)

### Non-Functional Requirements

#### NFR-1: Performance
- Active-contract option chain fetch adds ~1-2s per contract to outcome collection (acceptable — batch operation)
- Short interest extraction adds no latency (already in yfinance `info` dict)
- Signal classification is pure frontend logic (zero API cost)

#### NFR-2: Backward Compatibility
- `OutcomeCollector` without `OptionsDataService` behaves exactly as before
- `TickerInfo` new fields default to `None` — no migration needed
- `MarketContext` new field defaults to `None` — no DB migration

#### NFR-3: Data Quality
- Option chain fetched for P&L may have stale quotes (after-hours) — acceptable for directional P&L
- Short interest from yfinance may be delayed (typically 2x/month reports) — acceptable
- Signal interpretation is approximate (percentile-based, not raw value) — label accordingly

## Success Criteria

| Metric | Target |
|--------|--------|
| Active contracts have `exit_contract_mid` populated | Yes (when OptionsDataService available) |
| Analytics charts show non-expired contract data | Yes |
| `TickerInfo.short_ratio` populated from yfinance | Yes (when available) |
| Fundamental agent receives short interest data | Yes |
| RSI/ADX/BB Width show interpretation labels | Yes |
| Indicator labels color-coded | Yes |

## Constraints & Assumptions

### Constraints
- Option chain fetch requires active market hours for accurate bid/ask
- Short interest data from yfinance may be None for many tickers (less popular stocks)
- Indicator interpretation thresholds are for normalized percentile values, not raw indicators

### Assumptions
- `OptionsDataService.fetch_chain()` can fetch a chain for a specific expiration date
- yfinance `shortRatio` and `shortPercentOfFloat` are available for most liquid equities
- Users prefer approximate interpretation labels over no guidance at all

## Out of Scope

- **Historical option pricing** (for retroactive P&L) — only live prices for active contracts
- **Short interest history/trend** — single snapshot only
- **Custom interpretation thresholds** — hardcoded for now; configurable later
- **Indicator tooltips with detailed explanations** — labels only for now

## Dependencies

### Internal
- `OptionsDataService` — exists, needs DI wiring into `OutcomeCollector`
- `api/deps.py` — `get_outcome_collector()` needs update
- `safe_float()` helper in `market_data.py` — exists for yfinance field extraction
- `DirectionBadge.vue` / PrimeVue `Tag` — pattern for colored badges exists

### External
- yfinance `shortRatio` / `shortPercentOfFloat` fields — available in `Ticker.info`

## Technical Design Reference

### File Changes

| File | Action | Purpose |
|------|--------|---------|
| `src/options_arena/services/outcome_collector.py` | Edit | Add `OptionsDataService` param, fetch option chain for active contracts |
| `src/options_arena/api/deps.py` | Edit | Pass `options_data` to `OutcomeCollector` |
| `src/options_arena/cli/commands/outcomes.py` | Edit | Pass `OptionsDataService` to collector |
| `src/options_arena/models/market_data.py` | Edit | Add `short_ratio`, `short_pct_of_float` to `TickerInfo` |
| `src/options_arena/services/market_data.py` | Edit | Extract short interest from yfinance info |
| `src/options_arena/models/analysis.py` | Edit | Add `short_ratio` to `MarketContext` |
| `src/options_arena/agents/_parsing.py` | Edit | Render short interest in context block |
| `web/src/components/TickerDrawer.vue` | Edit | Add signal interpretation labels + colors |

### Implementation Waves

| Wave | Tasks | Can Parallelize? |
|------|-------|-----------------|
| 1 | Short interest fields (TickerInfo + extraction) | Yes |
| 1 | Signal interpretation utility + TickerDrawer update | Yes (independent) |
| 2 | OptionsDataService DI into OutcomeCollector | After Wave 1 |
| 2 | MarketContext short_ratio + context block rendering | After Wave 1 |
| 3 | Testing: P&L computation, short interest propagation, signal labels | After Wave 2 |
