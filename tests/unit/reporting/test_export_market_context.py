"""Tests for debate export with MarketContext market snapshot (issue #176).

Tests cover:
  - Export with persisted MarketContext → verify real prices appear
  - Export gracefully handles MarketContext (always present on DebateResult)
  - Market Snapshot section contains expected table rows
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.models import AgentResponse, MarketContext, TradeThesis
from options_arena.models.enums import ExerciseStyle, MacdSignal, SignalDirection
from options_arena.reporting.debate_export import (
    DISCLAIMER,
    export_debate_markdown,
)


def _make_market_context(
    *,
    current_price: Decimal = Decimal("185.50"),
    contract_mid: Decimal | None = Decimal("3.45"),
) -> MarketContext:
    """Build a MarketContext with real prices."""
    return MarketContext(
        ticker="AAPL",
        current_price=current_price,
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
        contract_mid=contract_mid,
    )


def _make_bull_response() -> AgentResponse:
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings risk"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test-model",
    )


def _make_bear_response() -> AgentResponse:
    return AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="Sector rotation risk.",
        key_points=["Sector rotation underway"],
        risks_cited=["Momentum could extend"],
        contracts_referenced=["AAPL $180 PUT"],
        model_used="test-model",
    )


def _make_trade_thesis() -> TradeThesis:
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up"],
        risk_assessment="Moderate risk.",
    )


def _make_debate_result(
    *,
    current_price: Decimal = Decimal("185.50"),
    contract_mid: Decimal | None = Decimal("3.45"),
) -> DebateResult:
    """Build a complete DebateResult with MarketContext carrying real prices."""
    return DebateResult(
        context=_make_market_context(
            current_price=current_price,
            contract_mid=contract_mid,
        ),
        bull_response=_make_bull_response(),
        bear_response=_make_bear_response(),
        thesis=_make_trade_thesis(),
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )


# ---------------------------------------------------------------------------
# Export with real prices
# ---------------------------------------------------------------------------


def test_export_contains_market_snapshot_section() -> None:
    """Export includes a Market Snapshot section with real price data."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "## Market Snapshot" in md


def test_export_shows_real_current_price() -> None:
    """Market Snapshot shows the real current price from MarketContext."""
    result = _make_debate_result(current_price=Decimal("185.50"))
    md = export_debate_markdown(result)

    assert "$185.50" in md


def test_export_shows_52w_high_low() -> None:
    """Market Snapshot includes 52-week high and low prices."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "$199.62" in md
    assert "$164.08" in md


def test_export_shows_target_strike() -> None:
    """Market Snapshot shows the target strike price."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "$190.00" in md


def test_export_shows_contract_mid_when_present() -> None:
    """Market Snapshot shows contract mid when available."""
    result = _make_debate_result(contract_mid=Decimal("3.45"))
    md = export_debate_markdown(result)

    assert "$3.45" in md


def test_export_omits_contract_mid_when_none() -> None:
    """Market Snapshot omits contract mid row when it is None."""
    result = _make_debate_result(contract_mid=None)
    md = export_debate_markdown(result)

    assert "Contract Mid" not in md


def test_export_shows_iv_rank_and_percentile() -> None:
    """Market Snapshot includes IV Rank and IV Percentile values."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "IV Rank" in md
    assert "45.2" in md
    assert "IV Percentile" in md
    assert "52.1" in md


def test_export_still_has_all_sections() -> None:
    """Export with Market Snapshot still includes all other sections."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "## Market Snapshot" in md
    assert "## Bull Case" in md
    assert "## Bear Case" in md
    assert "## Verdict" in md
    assert DISCLAIMER in md


def test_export_with_different_price() -> None:
    """Export reflects a different current price correctly."""
    result = _make_debate_result(current_price=Decimal("420.69"))
    md = export_debate_markdown(result)

    assert "$420.69" in md
