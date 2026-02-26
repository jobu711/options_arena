"""Options Arena — Pydantic v2 models for options contracts and spreads.

Defines ``OptionGreeks``, ``OptionContract``, ``SpreadLeg``, and ``OptionSpread``.
All snapshot models (``OptionGreeks``, ``OptionContract``) are frozen.

Key design decisions:
- ``OptionGreeks.pricing_model`` tracks which model (BSM/BAW) produced the values.
- ``OptionContract.greeks`` is always ``None`` from yfinance — populated later by
  ``pricing/dispatch.py``, which is the sole source of Greeks.
- ``OptionContract.market_iv`` is the yfinance ``impliedVolatility`` passthrough,
  used as IV solver seed and sanity-check against locally computed IV.
- ``mid`` divides by ``Decimal("2")`` to preserve full Decimal precision.
- All ``Decimal`` fields use ``field_serializer`` to prevent float precision loss in JSON.
"""

import math
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer, field_validator

from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PositionSide,
    PricingModel,
    SpreadType,
)


class OptionGreeks(BaseModel):
    """Sensitivity measures for an option contract.

    Validated at the boundary to prevent bad data from pricing edge cases
    from corrupting downstream calculations.

    Attributes:
        delta: Price sensitivity, must be in [-1.0, 1.0].
        gamma: Delta acceleration, must be >= 0.
        theta: Time decay, usually negative (no validation — time decay costs money).
        vega: Volatility sensitivity, must be >= 0.
        rho: Interest rate sensitivity, small value with either sign.
        pricing_model: Which model (BSM or BAW) produced these Greeks.
    """

    model_config = ConfigDict(frozen=True)

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    pricing_model: PricingModel

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, v: float) -> float:
        """Ensure delta is finite and within [-1.0, 1.0]."""
        if not math.isfinite(v) or not -1.0 <= v <= 1.0:
            raise ValueError(f"delta must be finite and in [-1.0, 1.0], got {v}")
        return v

    @field_validator("gamma", "vega")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        """Ensure gamma and vega are finite and non-negative."""
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"must be finite and >= 0, got {v}")
        return v

    @field_validator("theta", "rho")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Ensure theta and rho are finite (allow negative values).

        Theta is normally negative (time decay costs money).
        Rho can be either sign depending on option type and rate direction.
        """
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class OptionContract(BaseModel):
    """A single option contract with market data and optional computed Greeks.

    ``greeks`` is always ``None`` when constructed from yfinance data — it is
    populated after local computation by ``pricing/dispatch.py``.
    ``market_iv`` is the yfinance ``impliedVolatility`` passthrough used as
    IV solver seed and sanity-check against locally computed IV.

    Attributes:
        ticker: Underlying ticker symbol.
        option_type: CALL or PUT.
        strike: Strike price (Decimal, string-constructed).
        expiration: Expiration date (datetime.date, never string).
        bid: Bid price.
        ask: Ask price.
        last: Last traded price.
        volume: Trading volume (whole number).
        open_interest: Open interest (whole number).
        exercise_style: AMERICAN or EUROPEAN — drives pricing dispatch.
        market_iv: yfinance impliedVolatility passthrough (solver seed).
        greeks: Computed Greeks, or None if not yet computed.
        mid: Computed mid price ``(bid + ask) / 2``.
        spread: Computed bid-ask spread ``ask - bid``.
        dte: Computed days to expiration from today.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    option_type: OptionType
    strike: Decimal
    expiration: date
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: int
    open_interest: int
    exercise_style: ExerciseStyle
    market_iv: float
    greeks: OptionGreeks | None = None

    @field_validator("market_iv")
    @classmethod
    def validate_market_iv_non_negative(cls, v: float) -> float:
        """Ensure market_iv is finite and non-negative."""
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"market_iv must be finite and >= 0, got {v}")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid(self) -> Decimal:
        """Mid price: ``(bid + ask) / Decimal("2")``."""
        return (self.bid + self.ask) / Decimal("2")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def spread(self) -> Decimal:
        """Bid-ask spread: ``ask - bid``."""
        return self.ask - self.bid

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dte(self) -> int:
        """Days to expiration from today."""
        return (self.expiration - date.today()).days

    @field_serializer("strike", "bid", "ask", "last")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to string to prevent float precision loss."""
        return str(v)


class SpreadLeg(BaseModel):
    """A single leg of an option spread.

    Attributes:
        contract: The option contract for this leg.
        side: LONG or SHORT position.
        quantity: Number of contracts (defaults to 1, must be >= 1).
    """

    contract: OptionContract
    side: PositionSide
    quantity: int = 1

    @field_validator("quantity")
    @classmethod
    def validate_quantity_positive(cls, v: int) -> int:
        """Ensure quantity is at least 1."""
        if v < 1:
            raise ValueError(f"quantity must be >= 1, got {v}")
        return v


class OptionSpread(BaseModel):
    """A multi-leg option spread strategy.

    Attributes:
        spread_type: Type of spread (vertical, calendar, iron condor, etc.).
        legs: List of spread legs composing this strategy (at least 1).
        ticker: Underlying ticker symbol.
    """

    spread_type: SpreadType
    legs: list[SpreadLeg]
    ticker: str

    @field_validator("legs")
    @classmethod
    def validate_legs_not_empty(cls, v: list[SpreadLeg]) -> list[SpreadLeg]:
        """Ensure at least one leg in the spread."""
        if len(v) < 1:
            raise ValueError("legs must contain at least 1 spread leg")
        return v
