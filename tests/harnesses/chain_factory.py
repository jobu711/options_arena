"""Synthetic option chain builder for contract selection edge case tests.

Provides ``ChainSpec`` for configuring edge cases and ``build_chain()`` for
constructing lists of ``OptionContract`` instances with those characteristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from options_arena.models.enums import ExerciseStyle, GreeksSource, OptionType, PricingModel
from options_arena.models.options import OptionContract, OptionGreeks


@dataclass
class ChainSpec:
    """Specification for a synthetic option chain.

    Attributes:
        ticker: Underlying ticker symbol.
        spot: Current underlying price.
        option_type: CALL or PUT.
        num_strikes: Number of contracts to generate.
        strike_start: Lowest strike price.
        strike_step: Increment between strikes.
        dte_days: Days to expiration.
        base_bid: Default bid price for each contract.
        base_ask: Default ask price for each contract.
        base_volume: Default volume.
        base_oi: Default open interest.
        base_iv: Default implied volatility.
        base_delta: Default delta (absolute value; sign applied per option_type).
        zero_bid_indices: Contract indices that get bid=0 (zero-bid edge case).
        stale_bid_gt_ask_indices: Contract indices where bid > ask (stale quote).
        nan_delta_indices: Contract indices that get NaN delta.
        wide_spread_indices: Contract indices with extremely wide spreads.
        zero_oi_indices: Contract indices with open_interest=0.
        deep_itm_delta: Override delta for deep ITM contracts (indices).
        deep_itm_indices: Indices to apply deep_itm_delta override.
    """

    ticker: str = "TEST"
    spot: float = 100.0
    option_type: OptionType = OptionType.CALL
    num_strikes: int = 10
    strike_start: float = 90.0
    strike_step: float = 2.5
    dte_days: int = 45
    base_bid: float = 3.00
    base_ask: float = 3.50
    base_volume: int = 200
    base_oi: int = 1000
    base_iv: float = 0.30
    base_delta: float = 0.40
    zero_bid_indices: list[int] = field(default_factory=list)
    stale_bid_gt_ask_indices: list[int] = field(default_factory=list)
    nan_delta_indices: list[int] = field(default_factory=list)
    wide_spread_indices: list[int] = field(default_factory=list)
    zero_oi_indices: list[int] = field(default_factory=list)
    deep_itm_delta: float = 0.90
    deep_itm_indices: list[int] = field(default_factory=list)


def build_chain(spec: ChainSpec) -> list[OptionContract]:
    """Build a synthetic option chain from a ``ChainSpec``.

    Returns a list of ``OptionContract`` instances with Greeks pre-populated.
    Edge cases (NaN delta, zero bid, stale quotes, etc.) are applied per the spec.
    """
    expiration = datetime.now(UTC).date() + timedelta(days=spec.dte_days)
    contracts: list[OptionContract] = []

    for i in range(spec.num_strikes):
        strike = spec.strike_start + i * spec.strike_step
        bid = spec.base_bid
        ask = spec.base_ask
        volume = spec.base_volume
        oi = spec.base_oi
        delta = spec.base_delta

        # Apply edge cases
        if i in spec.zero_bid_indices:
            bid = 0.0
            ask = spec.base_ask
        if i in spec.stale_bid_gt_ask_indices:
            bid = spec.base_ask + 1.0  # bid > ask
            ask = spec.base_ask
        if i in spec.wide_spread_indices:
            bid = 0.50
            ask = 10.00  # ~180% spread
        if i in spec.zero_oi_indices:
            oi = 0
        if i in spec.deep_itm_indices:
            delta = spec.deep_itm_delta

        # Build Greeks (or NaN delta)
        greeks: OptionGreeks | None = None
        if i in spec.nan_delta_indices:
            # OptionGreeks validates delta in [-1,1], so we bypass validation
            # via model_construct to inject NaN for testing edge cases.
            greeks = OptionGreeks.model_construct(
                delta=float("nan"),
                gamma=0.01,
                theta=-0.05,
                vega=0.10,
                rho=0.01,
                pricing_model=PricingModel.BAW,
            )
        else:
            # Apply sign convention: puts have negative delta
            signed_delta = -delta if spec.option_type == OptionType.PUT else delta
            greeks = OptionGreeks(
                delta=signed_delta,
                gamma=0.05,
                theta=-0.03,
                vega=0.15,
                rho=0.01,
                pricing_model=PricingModel.BAW,
            )

        contract = OptionContract(
            ticker=spec.ticker,
            option_type=spec.option_type,
            strike=Decimal(str(strike)),
            expiration=expiration,
            bid=Decimal(str(bid)),
            ask=Decimal(str(ask)),
            last=Decimal(str((bid + ask) / 2)),
            volume=volume,
            open_interest=oi,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=spec.base_iv,
            greeks=greeks,
            greeks_source=GreeksSource.COMPUTED,
        )
        contracts.append(contract)

    return contracts
