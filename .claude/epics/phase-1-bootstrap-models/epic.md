---
name: phase-1-bootstrap-models
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/1
updated: 2026-02-22T17:32:40Z
---

# Epic 1: Project Bootstrap & Models

## Overview

Initialize the `options_arena` project from scratch and build the complete models layer that every other module imports from. This is the foundation — nothing else can start until this is done.

## Scope

### PRD Requirements Covered
FR-M1, FR-M2, FR-M3, FR-M3.1, FR-M4, FR-M5, FR-M5.1, FR-M6, FR-M7, FR-M8, NFR-1 through NFR-11

### Deliverables

**Project setup:**
- `uv init` with `pyproject.toml` — all runtime + dev dependencies
- ruff config (Python 3.13, line length 99, rules: E, F, I, UP, B, SIM, ANN)
- mypy config (`strict = true`)
- pytest config (asyncio mode)
- `src/options_arena/__init__.py` with version

**Models (`src/options_arena/models/`):**
- `enums.py` — `OptionType`, `PositionSide`, `SignalDirection`, `ExerciseStyle`, `PricingModel`, `MarketCapTier`, `DividendSource`, `SpreadType`, `GreeksSource`
- `market_data.py` — `OHLCV`, `Quote`, `TickerInfo` (with `dividend_yield`, `dividend_source`, `dividend_rate`, `trailing_dividend_rate`)
- `options.py` — `OptionGreeks` (with `pricing_model`), `OptionContract` (with `exercise_style`, `market_iv`), `SpreadLeg`, `OptionSpread`
- `analysis.py` — `MarketContext`, `AgentResponse`, `TradeThesis`
- `scan.py` — `ScanRun`, `TickerScore` (with `IndicatorSignals` replacing `dict[str, float]`)
- `config.py` — `ScanConfig(BaseModel)`, `PricingConfig(BaseModel)`, `ServiceConfig(BaseModel)`, `AppSettings(BaseSettings)` with `SettingsConfigDict(env_prefix="ARENA_", env_nested_delimiter="__")`
- `health.py` — `HealthStatus`
- `__init__.py` — Re-export all public models

**Typed model: `IndicatorSignals`:**
- 18 named `float | None` fields: `rsi`, `stochastic_rsi`, `williams_r`, `adx`, `roc`, `supertrend`, `bb_width`, `atr_pct`, `keltner_width`, `obv`, `ad`, `relative_volume`, `sma_alignment`, `vwap_deviation`, `iv_rank`, `iv_percentile`, `put_call_ratio`, `max_pain_distance`

**Utils (`src/options_arena/utils/`):**
- `exceptions.py` — `DataFetchError`, `TickerNotFoundError`, `InsufficientDataError`, `DataSourceUnavailableError`, `RateLimitExceededError`

**Tests (`tests/unit/models/`):**
- All enums: member values, exhaustive iteration
- All models: construction, frozen behavior, computed fields, validation, serialization
- `AppSettings`: default construction, env var overrides, nested delimiter parsing
- `IndicatorSignals`: all-None, partial fill, serialization round-trip
- Exceptions: hierarchy, string representation
- ~150 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```
All three must pass before this epic is complete.

## Dependencies
- **Blocks**: Every other epic (2-8)
- **Blocked by**: Nothing — this is the starting point

## Key Decisions
- `AppSettings` is the sole `BaseSettings` subclass; `ScanConfig`/`PricingConfig`/`ServiceConfig` are nested `BaseModel`
- `frozen=True` on snapshot models (OHLCV, Quote, OptionContract, OptionGreeks)
- `Decimal` for prices/P&L, `float` for Greeks/IV/indicators, `int` for volume/OI
- All yfinance-facing field names use snake_case in models (camelCase translation in services layer)

## Estimated Tests: ~150

## Tasks Created
- [ ] #3 - Project scaffold & tooling configuration (parallel: false)
- [ ] #5 - Enums & exception hierarchy (parallel: false, depends: #3)
- [ ] #7 - Market data models — OHLCV, Quote, TickerInfo (parallel: true, depends: #5)
- [ ] #9 - Options models — OptionGreeks, OptionContract, SpreadLeg, OptionSpread (parallel: true, depends: #5)
- [ ] #11 - Analysis, scan & health models (parallel: true, depends: #5)
- [ ] #2 - Config models with AppSettings (parallel: true, depends: #3)
- [ ] #4 - Package re-exports __init__.py (parallel: false, depends: #5, #7, #9, #11, #2)
- [ ] #6 - Unit tests — enums, exceptions & config ~45 tests (parallel: true, depends: #5, #2)
- [ ] #8 - Unit tests — data models, validation & serialization ~105 tests (parallel: true, depends: #7, #9, #11, #4)
- [ ] #10 - Verification gate — ruff + mypy + pytest all green (parallel: false, depends: #4, #6, #8)

Total tasks: 10
Parallel tasks: 6 (#7, #9, #11, #2, #6, #8)
Sequential tasks: 4 (#3, #5, #4, #10)
Estimated total effort: 32-42 hours
