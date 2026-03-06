# Pydantic Model + API Schema — Prompt Template for Options Arena

> Use this template when designing a new Pydantic v2 model, extending an existing model, or adding API schema types in `models/`.

## The Template

```xml
<role>
You are a data model architect specializing in Pydantic v2 for financial applications.
You design models with correct financial precision types (Decimal for prices, float
for Greeks, int for volume), proper immutability boundaries (frozen snapshots vs
mutable accumulators), and comprehensive field validators (UTC enforcement, confidence
bounds, isfinite guards). Your work matters because a model with wrong types or
missing validators silently corrupts every module that consumes it.
</role>

<context>
### Architecture Boundaries (models/)

| Rule | Detail |
|------|--------|
| No business logic | Models define data shapes only. No computation, no I/O. |
| No imports from other modules | models/ imports nothing from services/, pricing/, indicators/, etc. |
| Typed boundaries everywhere | Every piece of data crossing a module boundary is a typed model from here. |
| Re-export in __init__.py | Consumers import from the package: `from options_arena.models import X` |

### Financial Precision Rules

| Data Type | Python Type | Construction | Examples |
|-----------|------------|--------------|----------|
| Prices, P&L, cost basis | `Decimal` | From string: `Decimal("185.50")` | strike, bid, ask, last, current_price |
| Greeks, IV, indicators | `float` | Direct: `0.45` | delta, gamma, iv_rank, rsi |
| Volume, open interest | `int` | Direct: `1500` | volume, open_interest |
| Expiration dates | `date` | `datetime.date` | expiration |
| Timestamps | `datetime` | `datetime.datetime` with UTC | data_timestamp, checked_at |
| Categorical fields | `StrEnum` | From `enums.py` | OptionType, ExerciseStyle, PricingModel |

### Frozen vs Mutable Decision Matrix

| Frozen (frozen=True) | Mutable (default) |
|----------------------|-------------------|
| Snapshots: Quote, OHLCV, OptionContract, OptionGreeks | Accumulators: IndicatorSignals, TickerScore |
| Analysis results: AgentResponse, TradeThesis | Config: ScanConfig, PricingConfig |
| Persisted records: ScanRun, HealthStatus | In-progress state |
| Anything returned by services that shouldn't change | Anything populated incrementally |

### Pydantic v2 Patterns (Context7-Verified)

**frozen=True**:
```python
from pydantic import BaseModel, ConfigDict
class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True)
```

**computed_field**:
```python
from pydantic import computed_field
@computed_field
@property
def mid(self) -> Decimal:
    return (self.bid + self.ask) / Decimal("2")
```

**field_serializer** (for Decimal):
```python
from pydantic import field_serializer
@field_serializer("strike", "bid", "ask", "last")
def serialize_decimal(self, v: Decimal) -> str:
    return str(v)
```

**field_validator**:
```python
from pydantic import field_validator
@field_validator("confidence")
@classmethod
def validate_confidence(cls, v: float) -> float:
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"confidence must be in [0, 1], got {v}")
    return v
```

### UTC Enforcement Pattern

```python
from datetime import datetime, timedelta

@field_validator("timestamp")
@classmethod
def _validate_utc(cls, v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() != timedelta(0):
        raise ValueError("must be UTC")
    return v
```

### isfinite Guard Pattern

```python
import math

@field_validator("market_iv")
@classmethod
def _validate_finite(cls, v: float) -> float:
    if not math.isfinite(v):
        raise ValueError(f"must be finite, got {v}")
    if v < 0.0:
        raise ValueError(f"must be >= 0, got {v}")
    return v
```

### StrEnum Pattern

```python
from enum import StrEnum

class NewCategory(StrEnum):
    VALUE_A = "value_a"
    VALUE_B = "value_b"
```

### Re-Export Pattern (__init__.py)

```python
from options_arena.models.{{module}} import NewModel
# Add to __all__ list in the appropriate section
```

### Configuration Pattern

```python
# Nested sub-configs are BaseModel, NOT BaseSettings
class NewConfig(BaseModel):
    threshold: float = 0.5

# Only AppSettings is BaseSettings
class AppSettings(BaseSettings):
    new_config: NewConfig = NewConfig()
```

### Existing Model Reference: OptionContract

```python
class OptionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType                    # StrEnum, not raw string
    strike: Decimal                            # Decimal("185.00"), not float
    expiration: date                           # datetime.date, not string
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int
    open_interest: int
    exercise_style: ExerciseStyle              # StrEnum
    market_iv: float                           # float for IV (speed over precision)
    greeks: OptionGreeks | None = None         # None from yfinance, populated by pricing/

    @computed_field
    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")  # Decimal("2"), not int 2

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
</context>

<task>
Design {{MODEL_NAME}} as a new Pydantic v2 model (or extend {{EXISTING_MODEL}}) with:

1. Correct type choices for every field (Decimal/float/int per financial precision rules)
2. frozen=True or mutable decision based on the model's lifecycle
3. field_validators for all constrained fields (confidence, datetime, domain-specific)
4. field_serializer for all Decimal fields
5. computed_field for derived values
6. StrEnum definitions for any new categorical fields
7. Re-export in models/__init__.py
8. 5-test scaffold

The model represents: {{MODEL_PURPOSE_DESCRIPTION}}
</task>

<instructions>
### Decision Tree

1. **Frozen or mutable?**
   - Is this a snapshot/record (quote, contract, analysis result)? → `frozen=True`
   - Is it populated incrementally or updated after creation? → mutable (no frozen)
   - When in doubt, start frozen — you can always remove it later

2. **For each field, determine the type**:
   - Is it a price, cost, or monetary value? → `Decimal` (construct from strings)
   - Is it a Greek, IV, ratio, or indicator? → `float`
   - Is it a count (volume, OI, tickers)? → `int`
   - Is it a date (expiration)? → `datetime.date`
   - Is it a timestamp? → `datetime.datetime` + UTC validator
   - Is it a category with known values? → `StrEnum` from enums.py
   - Can it be absent? → `X | None = None` (never Optional[X])

3. **For each field, determine needed validators**:
   - `float` field with known range (confidence, probability)? → `field_validator` with bounds
   - `float` field representing a measurement? → `math.isfinite()` guard (NaN passes `>= 0`)
   - `datetime` field? → UTC enforcement validator
   - `Decimal` field? → `field_serializer` returning `str`
   - Domain constraint (delta in [-1,1], gamma >= 0)? → explicit `field_validator`

4. **For each derived value**:
   - Can it be computed from other fields? → `@computed_field @property`
   - Does it involve Decimal division? → Use `Decimal("2")` not int `2`

5. **StrEnum creation**:
   - Does a field have a fixed set of valid values?
   - Is there an existing StrEnum in enums.py that fits?
   - If not, create a new one with lowercase values: `VALUE = "value"`
</instructions>

<constraints>
1. Never return raw dicts from functions — always typed Pydantic models. This includes dict[str, float], dict[str, Any], and all dict variants.
2. Use Decimal (from strings: Decimal("185.50")) for prices — never float. Float has precision loss (1.05 → 1.0500000000000000444).
3. Validate Greek ranges: delta in [-1, 1], gamma >= 0, vega >= 0. Bad pricing edge cases corrupt everything downstream.
4. Use frozen=True on snapshot models: OptionContract, OptionGreeks, Quote, OHLCV, AgentResponse, TradeThesis.
5. Add field_serializer for every Decimal field — Pydantic silently converts Decimal to float in JSON without it.
6. Use X | None — never Optional[X]. Never import from typing. Python 3.13+ syntax.
7. Use lowercase list, dict — never typing.List, typing.Dict.
8. Use BaseModel (not BaseSettings) for sub-configs (ScanConfig, PricingConfig). Only AppSettings is BaseSettings.
9. dividend_yield is float with default 0.0, NEVER None. Waterfall fall-through is value is None, not falsy. 0.0 is valid data (growth stocks).
10. Set pricing_model on every OptionGreeks instance — PricingModel.BSM or PricingModel.BAW. Tracks provenance.
11. yfinance provides NO Greeks — only impliedVolatility. greeks on OptionContract is always None from yfinance, populated by pricing/dispatch.py.
12. mid divides by Decimal("2") — not int 2. Keeps full Decimal precision in computed field.
13. Use StrEnum for every categorical field with known values. Never raw str for fields like option_type, direction, exercise_style.
14. Enforce actual UTC on every datetime field — check both tzinfo is not None AND utcoffset() == timedelta(0). Reject naive and non-UTC.
15. Add field_validator on every confidence/probability field constraining to [0.0, 1.0]. Don't add it on one model and forget others.
16. Guard numeric validators with math.isfinite() BEFORE range checks — NaN silently passes v >= 0.
</constraints>

<examples>
### Example 1: OptionContract (frozen snapshot with Decimal + computed fields)

```python
# File: src/options_arena/models/options.py
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, computed_field, field_serializer

class OptionContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType              # StrEnum, NOT raw string
    strike: Decimal                      # Decimal("185.00"), NOT float
    expiration: date                     # datetime.date, NOT string
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int                          # Always whole number
    open_interest: int
    exercise_style: ExerciseStyle        # StrEnum
    market_iv: float                     # float for IV (speed over precision)
    greeks: OptionGreeks | None = None   # None from yfinance

    @computed_field
    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")  # Decimal("2"), NOT int 2

    @computed_field
    @property
    def dte(self) -> int:
        return (self.expiration - date.today()).days

    @field_serializer("strike", "bid", "ask", "last")
    def serialize_decimal(self, v: Decimal) -> str:
        return str(v)  # Prevents float precision loss in JSON
```

### Example 2: IndicatorSignals (mutable accumulator)

```python
# File: src/options_arena/models/scan.py
class IndicatorSignals(BaseModel):
    """18 named indicator fields. NOT frozen — populated incrementally."""
    # All fields float | None = None — None means indicator not computed
    rsi: float | None = None
    stochastic_rsi: float | None = None
    williams_r: float | None = None
    adx: float | None = None
    # ... 14 more fields
```

### Example 3: Validators (UTC + confidence + isfinite)

```python
# File: src/options_arena/models/analysis.py
import math
from datetime import datetime, timedelta
from pydantic import BaseModel, ConfigDict, field_validator

class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    confidence: float
    market_iv: float

    @field_validator("timestamp")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("market_iv")
    @classmethod
    def _validate_market_iv(cls, v: float) -> float:
        if not math.isfinite(v):       # isfinite FIRST — NaN passes v >= 0
            raise ValueError(f"must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"must be >= 0, got {v}")
        return v
```

### Example 4: New StrEnum + field_validator

```python
# File: src/options_arena/models/enums.py
class VolatilityRegime(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRISIS = "crisis"

# File: src/options_arena/models/analysis.py
class RegimeAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    regime: VolatilityRegime              # StrEnum, NOT raw str
    confidence: float
    # ... with field_validator on confidence
```
</examples>

<output_format>
Deliver in this order:

1. **Model class** with:
   - ConfigDict (frozen or mutable)
   - All fields with correct types
   - field_validators for constrained fields
   - field_serializer for Decimal fields
   - computed_field for derived values

2. **StrEnum definitions** (if any new categoricals) in enums.py

3. **__init__.py re-export update** — add to imports and __all__ list

4. **5-test scaffold**:
   - test_{{model}}_construction — happy path with valid data, assert all fields
   - test_{{model}}_frozen_or_mutable — frozen: raises on reassignment. Mutable: allows update.
   - test_{{model}}_serialization_roundtrip — model_validate_json(model_dump_json()) == original
   - test_{{model}}_validator_rejection — each validator rejects invalid input (NaN, out-of-range, non-UTC)
   - test_{{model}}_computed_fields — computed values are correct (mid, spread, dte, etc.)
</output_format>
```

## Quick-Reference Checklist

- [ ] Prices use `Decimal` (from strings), not `float`
- [ ] `field_serializer` on every `Decimal` field (prevents float precision loss in JSON)
- [ ] `frozen=True` on snapshot models
- [ ] UTC `field_validator` on every `datetime` field
- [ ] `[0.0, 1.0]` `field_validator` on every confidence/probability field
- [ ] `math.isfinite()` guard before range checks on numeric validators
- [ ] `StrEnum` for every categorical field (never raw `str`)
- [ ] `X | None` syntax (never `Optional[X]`, never `typing.List`/`Dict`)

## When to Use This Template

**Use when:**
- Creating a new data model for a module boundary
- Adding fields to an existing model (IndicatorSignals, MarketContext, etc.)
- Defining API response/request schemas for FastAPI endpoints
- Adding a new configuration sub-model to AppSettings

**Do not use when:**
- Implementing business logic (models/ has no logic)
- Working on indicator math (use Template 3: Indicator)
- Modifying agent prompts (use Template 1: Agent Design)
- Changing the pipeline flow (use Template 4: Pipeline)
