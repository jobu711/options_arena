# Analytics Persistence Layer — Plan

## Context

Options Arena computes rich data across a 4-phase pipeline (universe → indicators → contracts → persist) but discards most of it. The current persistence layer stores scan metadata, normalized indicator scores, and AI debate output — but throws away the contract recommendations, entry prices, normalization distributions, and has no mechanism to track whether signals were correct.

**The highest-alpha persistence target is outcome tracking** — closing the feedback loop so the system can answer: *"Did the BULLISH signal on AAPL from scan #42 actually make money?"*

This is the highest alpha because it:
1. Enables signal win rate measurement (% of BULLISH/BEARISH calls that were profitable)
2. Enables score calibration (is score 85+ actually better than 70-85?)
3. Enables indicator attribution (which of 58 signals predict returns?)
4. Enables optimal holding period analysis (when do gains peak post-signal?)
5. Creates supervised ML training data (X=indicators, y=P&L)
6. Enables contract recommendation quality audit (does delta 0.35 outperform?)

**SQLite remains the right engine.** Projected growth is ~240MB at 3 years of daily scans. The problems are missing tables and missing queries, not the database engine.

## What's Missing Today

| Data | Status | Alpha Value |
|------|--------|-------------|
| Recommended contracts (strike, expiry, bid, ask, IV, Greeks) | **Discarded after Phase 3** | Critical — can't track outcomes without entry point |
| Entry stock price at scan time | **Not captured** | Critical — P&L baseline |
| Exit prices (stock + contract) | **No collection mechanism** | Critical — closes the loop |
| Normalization distributions | **Ephemeral** | Medium — calibration context |
| Phase timing / failure reasons | **Discarded** | Low — operational observability |

## Implementation — 5 Waves

### Wave 1: Contract Persistence (Foundation)

Everything depends on this. Persist what Phase 3 computes.

**Migration `010_recommended_contracts.sql`:**
```sql
CREATE TABLE IF NOT EXISTS recommended_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    option_type TEXT NOT NULL,
    strike TEXT NOT NULL,              -- Decimal as TEXT
    expiration TEXT NOT NULL,          -- ISO date
    bid TEXT NOT NULL,
    ask TEXT NOT NULL,
    last TEXT,
    volume INTEGER NOT NULL,
    open_interest INTEGER NOT NULL,
    market_iv REAL NOT NULL,
    exercise_style TEXT NOT NULL,
    delta REAL, gamma REAL, theta REAL, vega REAL, rho REAL,
    pricing_model TEXT,
    greeks_source TEXT,
    entry_stock_price TEXT NOT NULL,   -- Decimal as TEXT
    entry_mid TEXT NOT NULL,           -- Decimal as TEXT
    direction TEXT NOT NULL,
    composite_score REAL NOT NULL,
    risk_free_rate REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(scan_run_id, ticker, option_type, strike, expiration)
);
CREATE INDEX IF NOT EXISTS idx_rc_scan_run ON recommended_contracts(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_rc_ticker ON recommended_contracts(ticker);
CREATE INDEX IF NOT EXISTS idx_rc_expiration ON recommended_contracts(expiration);
```

**New model** `RecommendedContract` in `src/options_arena/models/analytics.py` — frozen, Decimal fields with serializers, isfinite validators, UTC datetime validator.

**Pipeline integration:**
- Add `entry_prices: dict[str, Decimal]` to `OptionsResult` (scan/models.py)
- Capture `spot` price in `_process_ticker_options` (Phase 3), propagate to persist
- In `_phase_persist` (Phase 4): build `RecommendedContract` list from `OptionsResult.recommendations` + entry prices, call `repo.save_recommended_contracts()`

**Repository methods:** `save_recommended_contracts()`, `get_contracts_for_scan()`, `get_contracts_for_ticker()`

**Files touched:**
- NEW: `data/migrations/010_recommended_contracts.sql`
- NEW: `src/options_arena/models/analytics.py`
- EDIT: `src/options_arena/scan/models.py` (add entry_prices to OptionsResult)
- EDIT: `src/options_arena/scan/pipeline.py` (capture spot prices, persist contracts)
- EDIT: `src/options_arena/data/repository.py` (3 new methods)
- EDIT: `src/options_arena/models/__init__.py` (re-export)
- EDIT: `src/options_arena/data/__init__.py` (re-export)

**Tests:** ~40 (round-trip, Decimal precision, Greeks None handling, pipeline integration)

---

### Wave 2: Outcome Tracking

Define the outcome schema and provide collection mechanism.

**Migration `011_outcome_tracking.sql`:**
```sql
CREATE TABLE IF NOT EXISTS contract_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommended_contract_id INTEGER NOT NULL REFERENCES recommended_contracts(id),
    exit_stock_price TEXT,
    exit_contract_mid TEXT,
    exit_contract_bid TEXT,
    exit_contract_ask TEXT,
    exit_date TEXT,
    stock_return_pct REAL,
    contract_return_pct REAL,
    is_winner INTEGER,
    holding_days INTEGER,
    dte_at_exit INTEGER,
    collection_method TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    UNIQUE(recommended_contract_id, exit_date)
);
CREATE INDEX IF NOT EXISTS idx_co_rec_id ON contract_outcomes(recommended_contract_id);
```

**Key design:** Multiple outcomes per contract (T+1, T+5, T+10, T+20, at-expiry) to measure optimal holding period. Append-only — no UPDATE statements.

**New service** `OutcomeCollector` in `src/options_arena/services/outcome_collector.py`:
- Queries contracts from N days ago without outcomes at that holding period
- Fetches current stock quote + option chain for each
- Computes stock_return_pct and contract_return_pct
- Handles expired contracts (intrinsic value or worthless)
- Persists outcomes

**CLI command:** `options-arena outcomes [--holding-days 5] [--auto]`

**Files touched:**
- NEW: `data/migrations/011_outcome_tracking.sql`
- NEW: `src/options_arena/services/outcome_collector.py`
- EDIT: `src/options_arena/models/analytics.py` (add ContractOutcome, OutcomeCollectionMethod)
- EDIT: `src/options_arena/models/enums.py` (add OutcomeCollectionMethod StrEnum)
- EDIT: `src/options_arena/data/repository.py` (4 new methods)
- EDIT: `src/options_arena/cli/app.py` (add outcomes command)

**Tests:** ~35 (P&L computation, expired contracts, collector service)

---

### Wave 3: Normalization Metadata

Persist per-scan indicator distributions for calibration context.

**Migration `012_normalization_metadata.sql`:**
```sql
CREATE TABLE IF NOT EXISTS normalization_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    indicator_name TEXT NOT NULL,
    ticker_count INTEGER NOT NULL,
    min_value REAL, max_value REAL,
    median_value REAL, mean_value REAL, std_dev REAL,
    p25 REAL, p75 REAL,
    created_at TEXT NOT NULL,
    UNIQUE(scan_run_id, indicator_name)
);
CREATE INDEX IF NOT EXISTS idx_nm_scan_run ON normalization_metadata(scan_run_id);
```

**Integration:** Add `compute_normalization_stats()` in `scoring/normalization.py`, call in Phase 2, persist in Phase 4.

**Files touched:**
- NEW: `data/migrations/012_normalization_metadata.sql`
- EDIT: `src/options_arena/models/analytics.py` (add NormalizationStats)
- EDIT: `src/options_arena/scoring/normalization.py` (add stats computation)
- EDIT: `src/options_arena/scan/pipeline.py` (capture stats, persist)
- EDIT: `src/options_arena/data/repository.py` (2 new methods)

**Tests:** ~15

---

### Wave 4: Analytics Queries

Repository methods that answer the key alpha questions. No new tables.

**Methods:**
- `get_win_rate_by_direction()` → `list[WinRateResult]`
- `get_score_calibration(bucket_size)` → `list[ScoreCalibrationBucket]`
- `get_indicator_attribution(indicator, holding_days)` → `list[IndicatorAttributionResult]`
- `get_optimal_holding_period(direction)` → `list[HoldingPeriodResult]`
- `get_delta_performance(bucket_size, holding_days)` → `list[DeltaPerformanceResult]`
- `get_performance_summary(lookback_days)` → `PerformanceSummary`

All queries JOIN `recommended_contracts` with `contract_outcomes` and GROUP BY the relevant dimension.

**Result models** in `analytics.py` — all frozen, with isfinite validators.

**Tests:** ~30

---

### Wave 5: API Endpoints

Expose analytics to web UI.

**New route file** `src/options_arena/api/routes/analytics.py`:
- `GET /api/analytics/win-rate`
- `GET /api/analytics/score-calibration`
- `GET /api/analytics/indicator-attribution/{indicator}`
- `GET /api/analytics/holding-period`
- `GET /api/analytics/delta-performance`
- `GET /api/analytics/summary`
- `POST /api/analytics/collect-outcomes` (on-demand collection)
- `GET /api/analytics/scan/{scan_id}/contracts`

**Also:** Fix `get_ticker_detail` to return real contracts instead of `contracts=[]`.

**Configuration:** Add `AnalyticsConfig` to `AppSettings` (holding periods, auto-collect toggle, batch size).

**Tests:** ~25

---

## Verification

After each wave:
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

End-to-end validation after all waves:
1. Run a scan: `uv run options-arena scan --preset sp500`
2. Verify contracts persisted: query `recommended_contracts` table
3. Wait (or mock) holding period, run: `uv run options-arena outcomes --holding-days 1`
4. Verify outcomes: query `contract_outcomes` table
5. Hit analytics endpoints via web UI or curl
6. Verify win rate, score calibration queries return data

## Estimated Scope

- **~145 new tests** across all waves
- **3 new migrations** (010, 011, 012)
- **3 new files** (analytics models, outcome collector, analytics routes)
- **~10 edited files**
- Each wave is independently mergeable
