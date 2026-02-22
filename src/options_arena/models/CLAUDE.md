# CLAUDE.md — Data Models (`models/`)

## Purpose
All Pydantic v2 models, enums, and type definitions. No business logic. No I/O.
Every piece of data that crosses a module boundary is a typed model from here.

## Files

| File | Contents |
|------|----------|
| `enums.py` | `OptionType`, `PositionSide`, `SignalDirection`, `ExerciseStyle`, `PricingModel`, `MarketCapTier`, `DividendSource`, `SpreadType`, `GreeksSource` |
| `market_data.py` | `OHLCV`, `Quote`, `TickerInfo` |
| `options.py` | `OptionGreeks`, `OptionContract`, `SpreadLeg`, `OptionSpread` |
| `analysis.py` | `MarketContext`, `AgentResponse`, `TradeThesis` |
| `scan.py` | `IndicatorSignals`, `TickerScore`, `ScanRun` |
| `config.py` | `ScanConfig`, `PricingConfig`, `ServiceConfig`, `AppSettings` |
| `health.py` | `HealthStatus` |
| `__init__.py` | Re-exports all public models and enums |

---

## Pydantic v2 Rules (Context7-Verified)

- Import from `pydantic`, never `pydantic.v1`.
- `model_dump()` not `.dict()`. `field_validator` not `@validator`. `model_config = ConfigDict(...)`.
- `frozen=True` on snapshot models: `OHLCV`, `Quote`, `OptionContract`, `OptionGreeks`.
- JSON roundtrip must work: `Model.model_validate_json(m.model_dump_json()) == m`. Test this.

### frozen=True Pattern (Context7-Verified)
```python
from pydantic import BaseModel, ConfigDict

class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    # Raises ValidationError on attribute reassignment
```

### computed_field Pattern (Context7-Verified)
```python
from pydantic import BaseModel, computed_field

class MyModel(BaseModel):
    x: float
    y: float

    @computed_field
    @property
    def total(self) -> float:
        return self.x + self.y
# Included in model_dump() and JSON schema automatically
```

### field_serializer Pattern (Context7-Verified)
```python
from decimal import Decimal
from pydantic import BaseModel, field_serializer

class PriceModel(BaseModel):
    strike: Decimal

    @field_serializer("strike")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)
# Prevents Decimal -> float precision loss in JSON
```

### field_validator Pattern (Context7-Verified)
```python
from pydantic import BaseModel, field_validator

class RangeModel(BaseModel):
    value: float

    @field_validator("value")
    @classmethod
    def check_range(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"must be in [-1, 1], got {v}")
        return v
```

---

## Enums — All Use StrEnum

```python
from enum import StrEnum

class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"

class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"

class SignalDirection(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"

class ExerciseStyle(StrEnum):          # NEW — on every OptionContract
    AMERICAN = "american"
    EUROPEAN = "european"

class PricingModel(StrEnum):           # NEW — on OptionGreeks
    BSM = "bsm"
    BAW = "baw"

class MarketCapTier(StrEnum):          # NEW — replaces raw string "mid_cap"
    MEGA = "mega"
    LARGE = "large"
    MID = "mid"
    SMALL = "small"
    MICRO = "micro"

class DividendSource(StrEnum):         # NEW — provenance tracking on TickerInfo
    FORWARD = "forward"                # yfinance info["dividendYield"]
    TRAILING = "trailing"              # yfinance info["trailingAnnualDividendYield"]
    COMPUTED = "computed"              # sum(get_dividends("1y")) / price
    NONE = "none"                      # no dividend data available → 0.0

class SpreadType(StrEnum):
    VERTICAL = "vertical"
    CALENDAR = "calendar"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BUTTERFLY = "butterfly"

class GreeksSource(StrEnum):
    COMPUTED = "computed"
    MARKET = "market"
```

Never raw strings in business logic. Always `OptionType.CALL`, `ExerciseStyle.AMERICAN`.

---

## OptionContract — Required Shape

```python
class OptionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType
    strike: Decimal                        # string-constructed: Decimal("185.00")
    expiration: date                       # datetime.date, never string
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int
    open_interest: int
    exercise_style: ExerciseStyle          # NEW — AMERICAN for all U.S. equities
    market_iv: float                       # NEW — yfinance impliedVolatility passthrough
    greeks: OptionGreeks | None = None     # computed by pricing/dispatch.py, never yfinance

    @computed_field
    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @computed_field
    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @computed_field
    @property
    def dte(self) -> int:
        return (self.expiration - date.today()).days

    @field_serializer("strike", "bid", "ask", "last")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)
```

Key points:
- `exercise_style` drives pricing dispatch (BAW for AMERICAN, BSM for EUROPEAN).
- `market_iv` is yfinance's `impliedVolatility` — used as IV solver seed (Newton-Raphson for BSM) and sanity-check against locally computed IV.
- `greeks` is always `None` from yfinance. `pricing/dispatch.py` is the sole source of Greeks. The field is populated after local computation.
- `mid` divides by `Decimal("2")` not `2` — keeps full Decimal precision.

---

## OptionGreeks — Validate Ranges

```python
class OptionGreeks(BaseModel):
    model_config = ConfigDict(frozen=True)

    delta: float         # -1.0 to 1.0 (puts negative, calls positive)
    gamma: float         # >= 0
    theta: float         # usually negative (time decay costs money)
    vega: float          # >= 0
    rho: float           # small, either sign
    pricing_model: PricingModel  # NEW — BSM or BAW, tracks which model produced these

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"delta must be in [-1.0, 1.0], got {v}")
        return v

    @field_validator("gamma", "vega")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"must be >= 0, got {v}")
        return v
```

Validate at the boundary. Bad data from pricing edge cases corrupts everything downstream.

---

## TickerInfo — Dividend Yield with Provenance

```python
class TickerInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    company_name: str
    sector: str
    market_cap: int | None = None
    market_cap_tier: MarketCapTier | None = None

    # Dividend fields — populated by service layer 3-tier waterfall (FR-M7/M7.1)
    dividend_yield: float = 0.0            # decimal fraction (0.005 = 0.5%), NEVER None
    dividend_source: DividendSource = DividendSource.NONE
    dividend_rate: float | None = None     # forward annual $ — audit/cross-validation only
    trailing_dividend_rate: float | None = None  # trailing annual $ — audit only

    current_price: Decimal
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal
```

Critical rules:
- `dividend_yield` is `float`, default `0.0`, **never `None`**. Pricing engine receives a guaranteed float.
- All yfinance yield values are **decimal fractions** (0.005 = 0.5%), not percentages.
- `dividend_source` tracks which waterfall tier produced the value.
- `dividend_rate` / `trailing_dividend_rate` are audit fields for cross-validation — not used in pricing.
- Waterfall fall-through condition is `value is None`, NOT falsy. `0.0` is valid data (growth stocks).

---

## IndicatorSignals — Replaces `dict[str, float]`

```python
class IndicatorSignals(BaseModel):
    """18 named indicator fields. Replaces dict[str, float] on TickerScore.
    All fields are float | None — None means indicator could not be computed."""

    # Oscillators
    rsi: float | None = None
    stochastic_rsi: float | None = None
    williams_r: float | None = None

    # Trend
    adx: float | None = None
    roc: float | None = None
    supertrend: float | None = None

    # Volatility
    bb_width: float | None = None
    atr_pct: float | None = None
    keltner_width: float | None = None

    # Volume
    obv: float | None = None
    ad: float | None = None
    relative_volume: float | None = None

    # Moving Averages
    sma_alignment: float | None = None
    vwap_deviation: float | None = None

    # Options-specific
    iv_rank: float | None = None
    iv_percentile: float | None = None
    put_call_ratio: float | None = None
    max_pain_distance: float | None = None
```

- All 18 fields default to `None` — no indicator is required.
- This is a `BaseModel`, NOT frozen — scores get populated incrementally during pipeline.
- Values are **normalized 0-100** (percentile-ranked), not raw indicator values.
- Test: all-None construction, partial fill, serialization round-trip.

---

## ScanRun and TickerScore

```python
class ScanRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int | None = None                  # DB-assigned
    started_at: datetime                   # UTC
    completed_at: datetime | None = None
    preset: str                            # "full", "sp500", "etfs"
    tickers_scanned: int
    tickers_scored: int
    recommendations: int

class TickerScore(BaseModel):
    ticker: str
    composite_score: float                 # 0-100
    direction: SignalDirection
    signals: IndicatorSignals              # typed model, NOT dict[str, float]
    scan_run_id: int | None = None
```

---

## AppSettings — Configuration (Context7-Verified)

Pattern: `AppSettings(BaseSettings)` is the **sole** `BaseSettings` subclass.
`ScanConfig`, `PricingConfig`, `ServiceConfig` are plain `BaseModel` — NOT `BaseSettings`.
This is the pydantic-settings v2 pattern for nested config (Context7-verified).

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class ScanConfig(BaseModel):
    top_n: int = 50
    min_score: float = 0.0
    min_price: float = 10.0
    min_dollar_volume: float = 10_000_000.0
    ohlcv_min_bars: int = 200
    adx_trend_threshold: float = 15.0
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

class PricingConfig(BaseModel):
    risk_free_rate_fallback: float = 0.05
    delta_primary_min: float = 0.20
    delta_primary_max: float = 0.50
    delta_fallback_min: float = 0.10
    delta_fallback_max: float = 0.80
    delta_target: float = 0.35
    dte_min: int = 30
    dte_max: int = 60
    min_oi: int = 100
    min_volume: int = 1
    max_spread_pct: float = 0.10
    iv_solver_tol: float = 1e-6
    iv_solver_max_iter: int = 50

class ServiceConfig(BaseModel):
    yfinance_timeout: float = 15.0
    fred_timeout: float = 10.0
    ollama_timeout: float = 60.0
    rate_limit_rps: float = 2.0
    max_concurrent_requests: int = 5
    cache_ttl_market_hours: int = 300
    cache_ttl_after_hours: int = 3600
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",
    )

    scan: ScanConfig = ScanConfig()
    pricing: PricingConfig = PricingConfig()
    service: ServiceConfig = ServiceConfig()
```

Env override examples:
- `ARENA_SCAN__TOP_N=30` → `settings.scan.top_n == 30`
- `ARENA_PRICING__DELTA_TARGET=0.40` → `settings.pricing.delta_target == 0.40`
- `ARENA_SERVICE__OLLAMA_HOST=http://gpu:11434` → `settings.service.ollama_host`

Source priority (Context7-verified): init kwargs > env vars > field defaults.
`AppSettings()` with no args is a valid production config — all defaults are production-ready.
No `.env` file in MVP; add `env_file=".env"` later without model changes.

Dependency injection: `cli.py` creates `AppSettings()`, passes `settings.scan` to scan pipeline,
`settings.pricing` to pricing module, `settings.service` to services. Modules accept their config
slice, never the full `AppSettings`.

---

## MarketContext — Flat, Not Nested

```python
class MarketContext(BaseModel):
    """Snapshot of ticker state for analysis and (v2) debate agents.
    Keep flat — agents parse flat text better than nested objects."""
    ticker: str
    current_price: Decimal
    price_52w_high: Decimal
    price_52w_low: Decimal
    iv_rank: float
    iv_percentile: float
    atm_iv_30d: float
    rsi_14: float
    macd_signal: str                       # "bullish_crossover", "bearish_crossover", "neutral"
    put_call_ratio: float
    next_earnings: date | None
    dte_target: int
    target_strike: Decimal
    target_delta: float
    sector: str
    dividend_yield: float                  # decimal fraction, from TickerInfo
    exercise_style: ExerciseStyle          # for pricing dispatch
    data_timestamp: datetime

    @field_serializer("current_price", "price_52w_high", "price_52w_low", "target_strike")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)
```

---

## Analysis Models (Shapes for v2 Debate — Define Now)

```python
class AgentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: str                        # "bull", "bear", "risk"
    direction: SignalDirection
    confidence: float                      # 0.0 to 1.0
    argument: str
    key_points: list[str]
    risks_cited: list[str]
    contracts_referenced: list[str]        # specific strikes/expirations
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

class TradeThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float
    summary: str
    bull_score: float
    bear_score: float
    key_factors: list[str]
    risk_assessment: str
    recommended_strategy: SpreadType | None = None
```

---

## HealthStatus

```python
class HealthStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_name: str
    available: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime
```

---

## Decimal Serialization Rules

Pydantic silently converts `Decimal` to `float` in JSON, causing precision loss.
Every model with `Decimal` fields **must** have a `field_serializer` that converts to `str`.

```python
@field_serializer("strike", "bid", "ask", "last")
def serialize_decimal(self, v: Decimal) -> str:
    return str(v)
```

Test that `Decimal("1.05")` survives a JSON roundtrip without becoming `1.0500000000000000444`.

---

## Financial Precision Rules

| Data Type | Python Type | Construction | Examples |
|-----------|------------|--------------|----------|
| Prices, P&L, cost basis | `Decimal` | From string: `Decimal("185.50")` | strike, bid, ask, last, current_price |
| Greeks, IV, indicators | `float` | Direct: `0.45` | delta, gamma, iv_rank, rsi |
| Volume, open interest | `int` | Direct: `1500` | volume, open_interest, tickers_scanned |
| Expiration dates | `date` | `datetime.date` | expiration |
| Timestamps | `datetime` | `datetime.datetime` with UTC | data_timestamp, checked_at |

---

## Re-Export Pattern (`__init__.py`)

```python
"""Options Arena — Data Models."""

from options_arena.models.enums import (
    DividendSource,
    ExerciseStyle,
    GreeksSource,
    MarketCapTier,
    OptionType,
    PositionSide,
    PricingModel,
    SignalDirection,
    SpreadType,
)
from options_arena.models.market_data import OHLCV, Quote, TickerInfo
from options_arena.models.options import OptionContract, OptionGreeks, OptionSpread, SpreadLeg
from options_arena.models.analysis import AgentResponse, MarketContext, TradeThesis
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore
from options_arena.models.config import AppSettings, PricingConfig, ScanConfig, ServiceConfig
from options_arena.models.health import HealthStatus

__all__ = [
    # Enums
    "DividendSource",
    "ExerciseStyle",
    "GreeksSource",
    "MarketCapTier",
    "OptionType",
    "PositionSide",
    "PricingModel",
    "SignalDirection",
    "SpreadType",
    # Market data
    "OHLCV",
    "Quote",
    "TickerInfo",
    # Options
    "OptionContract",
    "OptionGreeks",
    "OptionSpread",
    "SpreadLeg",
    # Analysis
    "AgentResponse",
    "MarketContext",
    "TradeThesis",
    # Scan
    "IndicatorSignals",
    "ScanRun",
    "TickerScore",
    # Config
    "AppSettings",
    "PricingConfig",
    "ScanConfig",
    "ServiceConfig",
    # Health
    "HealthStatus",
]
```

Consumers import from the package: `from options_arena.models import OptionContract`.

---

## Test Requirements (~150 tests)

### Enums (`test_enums.py`)
- Each enum: member count, values, `StrEnum` subclass check, exhaustive iteration.
- `OptionType` has exactly 2 members. `SpreadType` has exactly 6. `DividendSource` has exactly 4. etc.

### Models — Construction & Frozen (`test_*.py`)
- Happy path: construct with valid data, assert all fields.
- Frozen: `pytest.raises(ValidationError)` on attribute reassignment for frozen models.
- Computed fields: `mid`, `spread`, `dte` return correct values.
- Validation: `OptionGreeks` rejects delta outside [-1, 1], gamma < 0, vega < 0.
- Defaults: `TickerInfo.dividend_yield` defaults to `0.0`, `dividend_source` defaults to `NONE`.

### Serialization (`test_serialization.py`)
- JSON roundtrip: `Model.model_validate_json(m.model_dump_json()) == m` for every model.
- Decimal precision: `Decimal("1.05")` survives roundtrip as `"1.05"` not `1.0500000...`.
- StrEnum serialization: `OptionType.CALL` serializes to `"call"` in JSON.

### AppSettings (`test_config.py`)
- Default construction: `AppSettings()` succeeds, all nested defaults correct.
- Env var override: monkeypatch `ARENA_SCAN__TOP_N=30`, assert `settings.scan.top_n == 30`.
- Nested delimiter: `ARENA_PRICING__DELTA_TARGET=0.40` works.
- Type coercion: string env vars correctly parsed to `int`, `float`.

### IndicatorSignals (`test_indicator_signals.py`)
- All-None: `IndicatorSignals()` constructs with all fields `None`.
- Partial fill: set 5 of 18 fields, rest remain `None`.
- Serialization round-trip.
- Field count: exactly 18 fields.

---

## What Claude Gets Wrong Here (Fix These)

1. **Raw dicts as fields** — `signals: dict[str, float]` is WRONG. Use `IndicatorSignals` with 18 named fields.
2. **float for prices** — `strike: float` is WRONG. Use `Decimal` with string construction.
3. **Skipping Greek validation** — Bad delta from pricing edge cases corrupts everything downstream. Validate at the boundary.
4. **Mutable snapshot models** — `OptionContract`, `OptionGreeks`, `Quote`, `OHLCV` MUST be `frozen=True`.
5. **Missing field_serializer** — Every model with `Decimal` fields needs `field_serializer` to prevent `float` precision loss in JSON.
6. **Optional[X] syntax** — Use `X | None`, never `Optional[X]`. Never import from `typing`.
7. **typing.List, typing.Dict** — Use `list`, `dict` lowercase. Python 3.13+.
8. **BaseSettings for sub-configs** — `ScanConfig`, `PricingConfig`, `ServiceConfig` are `BaseModel`, NOT `BaseSettings`. Only `AppSettings` is `BaseSettings`.
9. **None vs falsy for dividend_yield** — `dividend_yield` is `float` with default `0.0`, never `None`. Waterfall fall-through is `value is None`, not falsy.
10. **Forgetting pricing_model on OptionGreeks** — Every Greeks instance must track which pricing model (BSM/BAW) produced it.
11. **Assuming yfinance provides Greeks** — It does NOT. `greeks` on `OptionContract` is always `None` from yfinance, populated after local computation by `pricing/dispatch.py`.
12. **`mid` dividing by int 2** — Use `Decimal("2")` to keep full Decimal precision in the computed field.
