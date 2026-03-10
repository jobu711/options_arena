"""Shared fixtures for scoring unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from options_arena.models.config import PricingConfig, ScanConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from options_arena.models.scan import IndicatorSignals
from tests.factories import make_option_contract


@pytest.fixture()
def sample_signals_bullish() -> IndicatorSignals:
    """IndicatorSignals representing a strongly bullish ticker."""
    return IndicatorSignals(
        rsi=75.0,
        stochastic_rsi=80.0,
        williams_r=70.0,
        adx=85.0,
        roc=65.0,
        supertrend=70.0,
        atr_pct=30.0,
        bb_width=25.0,
        keltner_width=20.0,
        obv=80.0,
        ad=75.0,
        relative_volume=40.0,
        sma_alignment=90.0,
        vwap_deviation=60.0,
        iv_rank=55.0,
        iv_percentile=50.0,
        put_call_ratio=65.0,
        max_pain_distance=70.0,
    )


@pytest.fixture()
def sample_signals_bearish() -> IndicatorSignals:
    """IndicatorSignals representing a strongly bearish ticker."""
    return IndicatorSignals(
        rsi=25.0,
        stochastic_rsi=20.0,
        williams_r=30.0,
        adx=15.0,
        roc=35.0,
        supertrend=30.0,
        atr_pct=70.0,
        bb_width=75.0,
        keltner_width=80.0,
        obv=20.0,
        ad=25.0,
        relative_volume=60.0,
        sma_alignment=10.0,
        vwap_deviation=40.0,
        iv_rank=45.0,
        iv_percentile=50.0,
        put_call_ratio=35.0,
        max_pain_distance=30.0,
    )


@pytest.fixture()
def sample_signals_partial() -> IndicatorSignals:
    """IndicatorSignals with some indicators missing (None)."""
    return IndicatorSignals(
        rsi=60.0,
        adx=50.0,
        sma_alignment=55.0,
        # All options-specific indicators missing
        iv_rank=None,
        iv_percentile=None,
        put_call_ratio=None,
        max_pain_distance=None,
    )


@pytest.fixture()
def sample_signals_empty() -> IndicatorSignals:
    """IndicatorSignals with all fields None (default)."""
    return IndicatorSignals()


@pytest.fixture()
def default_scan_config() -> ScanConfig:
    """Default ScanConfig with production values."""
    return ScanConfig()


@pytest.fixture()
def default_pricing_config() -> PricingConfig:
    """Default PricingConfig with production values."""
    return PricingConfig()


def make_contract(
    *,
    ticker: str = "AAPL",
    option_type: OptionType = OptionType.CALL,
    strike: str = "150.00",
    dte_days: int = 45,
    bid: str = "5.00",
    ask: str = "5.50",
    last: str = "5.25",
    volume: int = 100,
    open_interest: int = 500,
    exercise_style: ExerciseStyle = ExerciseStyle.AMERICAN,
    market_iv: float = 0.30,
) -> OptionContract:
    """Convenience adapter around :func:`tests.factories.make_option_contract`.

    Accepts string prices (auto-coerced to ``Decimal`` by Pydantic) and
    ``dte_days`` (converted to an ``expiration`` date), keeping existing
    scoring-test call sites unchanged.

    .. deprecated::
        Prefer ``make_option_contract`` from ``tests.factories`` for new tests.
    """
    return make_option_contract(
        ticker=ticker,
        option_type=option_type,
        strike=Decimal(strike),
        expiration=datetime.now(UTC).date() + timedelta(days=dte_days),
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal(last),
        volume=volume,
        open_interest=open_interest,
        exercise_style=exercise_style,
        market_iv=market_iv,
    )
