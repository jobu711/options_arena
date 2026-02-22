# CLAUDE.md — Data Models

## Purpose
All Pydantic v2 models, enums, and type definitions. No business logic. No I/O.
Every piece of data that crosses a module boundary is a typed model from here.

## Files

## Pydantic v2 Only
- Import from `pydantic`, never `pydantic.v1`.
- `model_dump()` not `.dict()`. `field_validator` not `@validator`. `model_config = ConfigDict(...)`.
- `frozen=True` on immutable models (quotes, contracts, verdicts).
- JSON roundtrip must work: `Model.model_validate_json(m.model_dump_json()) == m`. Test this.

## Enums — Use StrEnum
```python
class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"

class SpreadType(StrEnum):
    VERTICAL = "vertical"
    CALENDAR = "calendar"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BUTTERFLY = "butterfly"
```
Never raw strings in business logic. Always `OptionType.CALL`, `SpreadType.IRON_CONDOR`.

## Options Contract Model — Required Shape
```python
class OptionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType
    strike: Decimal                     # string-constructed: Decimal("185.00")
    expiration: date                    # datetime.date, never string
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int
    open_interest: int
    implied_volatility: float
    greeks: OptionGreeks | None = None  # not all sources provide these

    @computed_field
    @property
    def mid(self) -> Decimal: return (self.bid + self.ask) / 2

    @computed_field
    @property
    def spread(self) -> Decimal: return self.ask - self.bid

    @computed_field
    @property
    def dte(self) -> int: return (self.expiration - date.today()).days
```

## Greeks Model — Validate Ranges
```python
class OptionGreeks(BaseModel):
    delta: float    # -1.0 to 1.0 (puts negative, calls positive)
    gamma: float    # >= 0
    theta: float    # usually negative (time decay costs money)
    vega: float     # >= 0
    rho: float      # small, either sign
```
Validate: delta ∈ [-1, 1], gamma ≥ 0, vega ≥ 0. Bad API data is common — reject it at the boundary.


## Debate Models — Options-Specific Fields
```python
class DebateArgument(BaseModel):
    position: SignalDirection            # bullish / bearish
    argument_text: str
    confidence: float                   # 0.0 to 1.0
    key_points: list[str]
    risks_cited: list[str]
    contracts_referenced: list[str]     # specific strikes/expirations discussed
    greeks_cited: GreeksCited            # typed model, NOT dict[str, float]
    model_used: str                     # "claude-sonnet-4-5-20250929" or "llama3:70b"

class DebateVerdict(BaseModel):
    winner: SignalDirection
    confidence: float
    summary: str
    bull_score: float
    bear_score: float
    key_factors: list[str]
    risk_assessment: str
    recommended_strategy: SpreadType | None
    disclaimer: str                     # ALWAYS populated from disclaimer.py
```

## MarketContext — Flat, Not Nested
```python
class MarketContext(BaseModel):
    """Snapshot passed to both debate agents. Keep flat — agents parse flat text better."""
    ticker: str
    current_price: Decimal
    price_52w_high: Decimal
    price_52w_low: Decimal
    iv_rank: float
    iv_percentile: float
    atm_iv_30d: float
    rsi_14: float
    macd_signal: str                    # "bullish_crossover", "bearish_crossover", "neutral"
    put_call_ratio: float
    next_earnings: date | None
    dte_target: int
    target_strike: Decimal
    target_delta: float
    sector: str
    data_timestamp: datetime
```
This is what agents receive. No nested objects — flat key-value pairs render better in prompts.

## Decimal Serialization
Pydantic will silently convert `Decimal` to `float` in JSON. Add a custom serializer:
```python
from pydantic import field_serializer

@field_serializer("strike", "bid", "ask", "last")
def serialize_decimal(self, v: Decimal) -> str:
    return str(v)
```
Test that `Decimal("1.05")` survives a JSON roundtrip without becoming `1.0500000000000000444`.

## What Claude Gets Wrong Here (Fix These)
- Don't use `dict[str, ...]` as a model field type — create a typed model instead. Example: `greeks_cited: dict[str, float]` is WRONG; use a `GreeksCited` model with named float fields.
- Don't use `float` for prices — `Decimal` with string construction.
- Don't skip Greek range validation — bad delta from APIs corrupts everything downstream.
- Don't create mutable models for data that shouldn't change — use `frozen=True`.
- Don't forget `disclaimer` field on `DebateVerdict` — every verdict needs it.
- Don't nest `MarketContext` deeply — agents handle flat structures better.
- Don't forget `contracts_referenced` and `greeks_cited` on `DebateArgument` — options debates must cite specifics.
- Don't let `Decimal` silently become `float` in JSON — add serializer, test roundtrip.