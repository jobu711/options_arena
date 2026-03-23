# CLAUDE.md -- Data Models (`models/`)

## Purpose

All Pydantic v2 models, enums, and type definitions. No business logic. No I/O.
Every piece of data that crosses a module boundary is a typed model from here.

Use Glob to discover files. Use `__init__.py` for available re-exports (~140 names).
Consumers import from the package: `from options_arena.models import OptionContract`.

---

## Pydantic v2 Rules

- Import from `pydantic`, never `pydantic.v1`.
- `model_dump()` not `.dict()`. `field_validator` not `@validator`.
  `model_config = ConfigDict(...)` not `class Config:`.
- `frozen=True` on snapshot models: `OHLCV`, `Quote`, `OptionContract`, `OptionGreeks`.
- JSON roundtrip must work: `Model.model_validate_json(m.model_dump_json()) == m`.
- `computed_field` properties are included in `model_dump()` and JSON schema automatically.
- `field_serializer` for Decimal fields -- serialize to `str` to prevent float precision loss.

---

## Enums -- 33 StrEnum Classes

All in `enums.py`, Python 3.13+ `enum.StrEnum` with lowercase string values.
Never raw strings in business logic. Always `OptionType.CALL`, `ExerciseStyle.AMERICAN`.

| Category | Enums |
|----------|-------|
| **Core options** | `OptionType`, `PositionSide`, `ExerciseStyle`, `SpreadType` |
| **Signals & direction** | `SignalDirection`, `MacdSignal`, `RiskLevel`, `CatalystImpact` |
| **Pricing & Greeks** | `PricingModel`, `GreeksSource`, `GreeksGroupBy`, `SurfaceMethod` |
| **Volatility** | `VolAssessment`, `VolRegime`, `VolRegimeTier`, `IVTermStructureShape` |
| **Market classification** | `MarketCapTier`, `MarketRegime`, `DividendSource` |
| **GICS taxonomy** | `GICSSector`, `GICSIndustryGroup` |
| **Scan & pipeline** | `ScanPreset`, `ScanSource`, `OutcomeCollectionMethod` |
| **Agent** | `LLMProvider`, `ConstraintViolationType`, `ConstraintSeverity` |
| **Routing/Eval** | `ModelTier`, `DeskRunStatus`, `ToolStatus` |
| **Valuation & macro** | `ValuationSignal`, `MacroRegime`, `FredTransform` |
| **Audit** | `AuditSeverity`, `AuditLayer` |

Also exported: `TICKER_RE` (compiled regex), `SECTOR_ALIASES`, `INDUSTRY_GROUP_ALIASES`,
`SECTOR_TO_INDUSTRY_GROUPS` (lookup dicts).

---

## OptionContract -- Critical Shape

Frozen model. Key field constraints:

- `strike`, `bid`, `ask`, `last`: `Decimal` (string-constructed: `Decimal("185.00")`)
- `expiration`: `datetime.date`, never string
- `volume`: `int`, `open_interest`: `int`
- `exercise_style`: `ExerciseStyle` -- drives pricing dispatch (BAW for AMERICAN, BSM for EUROPEAN)
- `market_iv`: `float` -- yfinance `impliedVolatility` passthrough. Already annualized. Used as
  IV solver seed and sanity-check. Do NOT re-annualize.
- `greeks: OptionGreeks | None = None` -- ALWAYS `None` from yfinance/services. `pricing/dispatch.py`
  is the sole source. Field populated after local computation.

Computed fields:
- `mid`: `(bid + ask) / Decimal("2")` -- divides by `Decimal("2")` not `2` for full precision.
- `spread`: `ask - bid`
- `dte`: `(expiration - date.today()).days`

All Decimal fields have `field_serializer` to `str` for JSON precision.

---

## OptionGreeks -- Validate Ranges

Frozen model. Every instance MUST set `pricing_model` (`PricingModel.BSM` or `PricingModel.BAW`).

| Field | Range | Notes |
|-------|-------|-------|
| `delta` | `[-1.0, 1.0]` | Puts negative, calls positive |
| `gamma` | `>= 0` | Always non-negative |
| `theta` | any | Usually negative (time decay costs money) |
| `vega` | `>= 0` | Always non-negative |
| `rho` | any | Small, either sign |
| `pricing_model` | BSM or BAW | Required -- tracks which model produced these |

Validate at the boundary. Bad data from pricing edge cases corrupts everything downstream.

---

## TickerInfo -- Dividend Yield with Provenance

Frozen model. Key dividend fields:

- `dividend_yield: float = 0.0` -- decimal fraction (0.005 = 0.5%), NEVER `None`. Pricing
  engine receives a guaranteed float.
- `dividend_source: DividendSource = DividendSource.NONE` -- tracks which waterfall tier
  produced the value (FORWARD, TRAILING, COMPUTED, NONE).
- `dividend_rate: float | None = None` -- forward annual $ amount, audit/cross-validation only.
- `trailing_dividend_rate: float | None = None` -- trailing annual $, audit only.

**Critical**: Waterfall fall-through condition is `value is None`, NOT falsy. `0.0` is valid
data for non-dividend-paying growth stocks. Checking `if not value:` skips `0.0` and corrupts
provenance tracking.

Also: `current_price: Decimal`, `fifty_two_week_high: Decimal`, `fifty_two_week_low: Decimal`,
`sector: str`, `market_cap_tier: MarketCapTier | None`.

---

## IndicatorSignals -- 18 Named Fields

Replaces `dict[str, float]`. All fields are `float | None`, default `None`.

- NOT frozen -- populated incrementally during pipeline.
- Values are **normalized 0-100** (percentile-ranked), not raw indicator values.
- All-None construction is valid.

Fields by category:
- **Oscillators**: `rsi`, `stochastic_rsi`, `williams_r`
- **Trend**: `adx`, `roc`, `supertrend`
- **Volatility**: `bb_width`, `atr_pct`, `keltner_width`
- **Volume**: `obv`, `ad`, `relative_volume`
- **Moving Averages**: `sma_alignment`, `vwap_deviation`
- **Options-specific**: `iv_rank`, `iv_percentile`, `put_call_ratio`, `max_pain_distance`

---

## ScanRun and TickerScore

**ScanRun**: Frozen. `id: int | None = None` (DB-assigned). `save_scan_run()` returns `int` ID.
Cannot mutate after construction -- callers reconstruct if they need one with ID set.

**TickerScore**: NOT frozen (direction updated after scoring).
- `composite_score: float` (0-100)
- `direction: SignalDirection`
- `signals: IndicatorSignals` -- typed model, NOT `dict[str, float]`
- `scan_run_id: int | None = None`

---

## MarketContext -- Flat, Not Nested

Snapshot of ticker state for analysis and recommendation agents. Keep flat -- agents parse
flat text better than nested objects.

Key fields: `ticker`, `current_price` (Decimal), `iv_rank`, `iv_percentile` (float | None),
`rsi_14`, `macd_signal`, `put_call_ratio`, `next_earnings` (date | None), `sector`,
`dividend_yield` (float), `exercise_style`, `data_timestamp` (datetime, UTC).

`completeness_ratio()` measures populated optional fields: <0.4 -> data-driven fallback;
<0.6 -> warning; >=0.6 -> full analysis.

All Decimal fields have `field_serializer` to `str`.

---

## AppSettings -- Configuration

`AppSettings(BaseSettings)` is the **sole** `BaseSettings` subclass. All nested configs
(`ScanConfig`, `PricingConfig`, `ServiceConfig`, `DebateConfig`, etc.) are plain `BaseModel`.

- Env prefix: `ARENA_`, nested delimiter: `__`
- Example: `ARENA_SCAN__TOP_N=30` -> `settings.scan.top_n == 30`
- Source priority: init kwargs > env vars > field defaults.
- `AppSettings()` with no args is a valid production config.
- DI pattern: `cli/` creates it, passes config slices to modules. Modules accept their
  slice, never the full `AppSettings`.

### Key Config Classes and Defaults

- `ScanConfig`: `top_n=50`, `min_score=0.0`, `min_price=10.0`, `min_dollar_volume=10_000_000.0`,
  `ohlcv_min_bars=200`, `adx_trend_threshold=15.0`, `rsi_overbought=70.0`, `rsi_oversold=30.0`
- `PricingConfig`: `risk_free_rate_fallback=0.05`, `delta_primary_min=0.20`, `delta_primary_max=0.50`,
  `delta_target=0.35`, `dte_min=30`, `dte_max=60`, `max_spread_pct=0.30`
- `ServiceConfig`: `yfinance_timeout=15.0`, `fred_timeout=10.0`, `rate_limit_rps=2.0`,
  `max_concurrent_requests=5`
- `DebateConfig`: includes `RoutingConfig` for model tier selection, `enable_model_routing` (default False)

---

## Recommendation Models

- `DomainAssessment` base + 6 subclasses (`TrendAssessment`, `VolatilityAssessment`,
  `FlowAssessment`, `FundamentalAssessment`, `RiskDeskAssessment`, `ContrarianAssessment`)
- `AnyAssessment`: discriminated union via `Discriminator("desk")` + `Tag()` for polymorphic
  JSON round-trip
- `PositionRecommendation`: 21 fields, `LLMDecimal` prices (not bare `Decimal`), frozen
- `RecommendationResult`: wraps context + assessments + recommendation + `RunUsage`
  (`arbitrary_types_allowed=True` for RunUsage)
- `DeskMetrics`: per-desk timing (`duration_ms`), model selection (`model_tier`, `model_used`), tokens
- `AssessmentSummary`: direction votes, avg confidence, disagreement desks, risk flags
- `RecommendationCost`: aggregated tokens + estimated USD cost

**LLMDecimal**: `Annotated[Decimal, WithJsonSchema({"type": "string"})]` -- Groq rejects
Pydantic's Decimal regex pattern. Use for ALL agent output Decimal fields.

---

## Model Routing Models

- `ModelTier` StrEnum: FAST, STANDARD, PREMIUM
- `RoutingConfig` on `DebateConfig`: `enable_model_routing` (opt-in), complexity thresholds,
  tier model names, cost pricing map (`cost_per_million_tokens`)

---

## Eval Harness Models

- `EvalDefinition`: YAML-loaded eval definitions with expected outputs
- `EvalRun`: persisted eval execution with pass@k scoring
- `EvalBaseline`: reference outputs for regression detection
- `EvalConfig` on `AppSettings`: `eval_dir`, `pass_at_k`, `model_grader_provider`

---

## Tool Response Model

- `ToolResponse`: frozen model with `ToolStatus` enum (SUCCESS/WARNING/ERROR) + typed `data` field
- All desk agent tool wrappers return `ToolResponse` instead of raw strings

---

## Decimal Serialization Rules

Pydantic silently converts `Decimal` to `float` in JSON, causing precision loss. Every model
with `Decimal` fields **must** have a `field_serializer` that converts to `str`.

Test that `Decimal("1.05")` survives a JSON roundtrip without becoming `1.0500000000000000444`.

---

## Financial Precision Rules

| Data Type | Python Type | Construction | Examples |
|-----------|------------|--------------|----------|
| Prices, P&L, cost | `Decimal` | From string: `Decimal("185.50")` | strike, bid, ask, last |
| Greeks, IV, indicators | `float` | Direct: `0.45` | delta, gamma, iv_rank, rsi |
| Volume, open interest | `int` | Direct: `1500` | volume, open_interest |
| Expiration dates | `date` | `datetime.date` | expiration |
| Timestamps | `datetime` | `datetime.datetime` with UTC | data_timestamp, checked_at |

---

## What Claude Gets Wrong Here (Fix These)

1. **Raw dicts as fields** -- `signals: dict[str, float]` is WRONG. Use `IndicatorSignals`.
2. **float for prices** -- `strike: float` is WRONG. Use `Decimal` with string construction.
3. **Skipping Greek validation** -- Bad delta from pricing edge cases corrupts everything downstream.
4. **Mutable snapshot models** -- `OptionContract`, `OptionGreeks`, `Quote`, `OHLCV` MUST be frozen.
5. **Missing field_serializer** -- Every Decimal model needs it. Prevents float precision loss in JSON.
6. **`Optional[X]` syntax** -- Use `X | None`. Never import from `typing`.
7. **`typing.List`, `typing.Dict`** -- Use lowercase `list`, `dict`. Python 3.13+.
8. **BaseSettings for sub-configs** -- Only `AppSettings` is `BaseSettings`. Nested configs are `BaseModel`.
9. **None vs falsy for dividend_yield** -- `float` default `0.0`, never `None`. Waterfall uses `is None`.
10. **Forgetting pricing_model on OptionGreeks** -- Every instance must track BSM or BAW.
11. **Assuming yfinance provides Greeks** -- It does NOT. `greeks` always `None` from yfinance.
12. **`mid` dividing by int 2** -- Use `Decimal("2")` for Decimal precision.
13. **Raw strings for categorical fields** -- Use StrEnum from `enums.py`. Every categorical
    field must have a corresponding enum.
14. **Timezone-aware != UTC** -- Enforce `v.utcoffset() != timedelta(0)`. Every `datetime` field
    needs validator rejecting both naive and non-UTC.
15. **Missing confidence validators** -- Every `confidence: float` must have `[0.0, 1.0]` validator.
16. **Unbounded domain floats** -- `market_iv >= 0`, `quantity >= 1`, `legs` non-empty. Add validators.
