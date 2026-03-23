"""Shared fixtures for scoring unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionContract
from tests.factories import make_option_contract


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
