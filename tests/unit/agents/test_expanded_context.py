"""Tests for expanded MarketContext fields (#72), build_market_context (#73),
render_context_block conditional rendering (#74).

Tests cover:
  - MarketContext construction with all new fields populated
  - MarketContext backward compatibility (new fields use defaults)
  - render_context_block includes non-None indicators, omits None
  - MarketContext rejects non-finite values (NaN, Inf) at construction
  - contract_mid Decimal serialization round-trip
  - build_market_context populates new fields from TickerScore and OptionContract
  - build_market_context uses defaults when contracts list is empty
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from options_arena.agents._parsing import _render_optional, render_context_block
from options_arena.agents.orchestrator import build_market_context
from options_arena.models import (
    ExerciseStyle,
    IndicatorSignals,
    MacdSignal,
    MarketContext,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KWARGS: dict[str, object] = {
    "ticker": "AAPL",
    "current_price": Decimal("185.50"),
    "price_52w_high": Decimal("199.62"),
    "price_52w_low": Decimal("164.08"),
    "iv_rank": 45.0,
    "iv_percentile": 52.0,
    "atm_iv_30d": 0.28,
    "rsi_14": 62.3,
    "macd_signal": MacdSignal.BULLISH_CROSSOVER,
    "put_call_ratio": 0.85,
    "next_earnings": None,
    "dte_target": 45,
    "target_strike": Decimal("190.00"),
    "target_delta": 0.35,
    "sector": "Technology",
    "dividend_yield": 0.005,
    "exercise_style": ExerciseStyle.AMERICAN,
    "data_timestamp": datetime(2026, 2, 25, 14, 0, 0, tzinfo=UTC),
}


def _make_context(**overrides: object) -> MarketContext:
    """Build a MarketContext with required fields, applying overrides."""
    kwargs = {**_REQUIRED_KWARGS, **overrides}
    return MarketContext(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MarketContext — New Field Tests (#72)
# ---------------------------------------------------------------------------


class TestMarketContextExpandedFields:
    """Tests for the 13 new MarketContext fields."""

    def test_all_new_fields_populated(self) -> None:
        """MarketContext accepts all 13 new fields with explicit values."""
        ctx = _make_context(
            composite_score=72.5,
            direction_signal=SignalDirection.BULLISH,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            stochastic_rsi=55.0,
            relative_volume=65.0,
            target_gamma=0.025,
            target_theta=-0.045,
            target_vega=0.32,
            target_rho=0.08,
            contract_mid=Decimal("4.65"),
        )
        assert ctx.composite_score == pytest.approx(72.5)
        assert ctx.direction_signal == SignalDirection.BULLISH
        assert ctx.adx == pytest.approx(28.4)
        assert ctx.sma_alignment == pytest.approx(0.7)
        assert ctx.bb_width == pytest.approx(42.1)
        assert ctx.atr_pct == pytest.approx(15.3)
        assert ctx.stochastic_rsi == pytest.approx(55.0)
        assert ctx.relative_volume == pytest.approx(65.0)
        assert ctx.target_gamma == pytest.approx(0.025)
        assert ctx.target_theta == pytest.approx(-0.045)
        assert ctx.target_vega == pytest.approx(0.32)
        assert ctx.target_rho == pytest.approx(0.08)
        assert ctx.contract_mid == Decimal("4.65")

    def test_backward_compatibility_defaults(self) -> None:
        """MarketContext constructs without new fields — all use defaults."""
        ctx = _make_context()
        assert ctx.composite_score == pytest.approx(0.0)
        assert ctx.direction_signal == SignalDirection.NEUTRAL
        assert ctx.adx is None
        assert ctx.sma_alignment is None
        assert ctx.bb_width is None
        assert ctx.atr_pct is None
        assert ctx.stochastic_rsi is None
        assert ctx.relative_volume is None
        assert ctx.target_gamma is None
        assert ctx.target_theta is None
        assert ctx.target_vega is None
        assert ctx.target_rho is None
        assert ctx.contract_mid is None

    def test_contract_mid_decimal_serialization_roundtrip(self) -> None:
        """contract_mid Decimal survives JSON serialization without precision loss."""
        ctx = _make_context(contract_mid=Decimal("5.25"))
        json_str = ctx.model_dump_json()
        restored = MarketContext.model_validate_json(json_str)
        assert restored.contract_mid == Decimal("5.25")
        assert restored == ctx

    def test_contract_mid_none_serialization_roundtrip(self) -> None:
        """contract_mid=None survives JSON roundtrip."""
        ctx = _make_context(contract_mid=None)
        json_str = ctx.model_dump_json()
        restored = MarketContext.model_validate_json(json_str)
        assert restored.contract_mid is None
        assert restored == ctx


# ---------------------------------------------------------------------------
# render_context_block — Conditional Rendering (#74)
# ---------------------------------------------------------------------------


class TestRenderContextBlockExpanded:
    """Tests for expanded render_context_block with new fields."""

    def test_includes_non_none_indicators(self) -> None:
        """Non-None indicator values appear in the rendered block."""
        ctx = _make_context(adx=75.0, bb_width=42.1, relative_volume=55.0)
        text = render_context_block(ctx)
        assert "ADX: 75.0" in text
        assert "BB WIDTH: 42.1" in text
        assert "REL VOLUME: 55.0" in text

    def test_omits_none_indicators(self) -> None:
        """None indicator values do NOT appear in the rendered block."""
        ctx = _make_context()  # all indicators are None by default
        text = render_context_block(ctx)
        assert "ADX" not in text
        assert "SMA ALIGNMENT" not in text
        assert "BB WIDTH" not in text
        assert "ATR %" not in text
        assert "STOCHASTIC RSI" not in text
        assert "REL VOLUME" not in text

    def test_rejects_nan_indicators(self) -> None:
        """NaN indicator values are rejected by MarketContext validators."""
        with pytest.raises(Exception, match="must be finite"):
            _make_context(adx=float("nan"))
        with pytest.raises(Exception, match="must be finite"):
            _make_context(bb_width=float("nan"))

    def test_rejects_inf_indicators(self) -> None:
        """Inf indicator values are rejected by MarketContext validators."""
        with pytest.raises(Exception, match="must be finite"):
            _make_context(atr_pct=float("inf"))
        with pytest.raises(Exception, match="must be finite"):
            _make_context(relative_volume=float("-inf"))

    def test_includes_greeks_when_set(self) -> None:
        """Non-None Greek values appear with .4f precision."""
        ctx = _make_context(
            target_gamma=0.025,
            target_theta=-0.045,
            target_vega=0.32,
            target_rho=0.08,
        )
        text = render_context_block(ctx)
        assert "GAMMA: 0.0250" in text
        assert "THETA: -0.0450" in text
        assert "VEGA: 0.3200" in text
        assert "RHO: 0.0800" in text

    def test_omits_greeks_when_none(self) -> None:
        """None Greek values do NOT appear in the rendered block."""
        ctx = _make_context()
        text = render_context_block(ctx)
        assert "GAMMA" not in text
        assert "THETA" not in text
        assert "VEGA" not in text
        assert "RHO" not in text

    def test_includes_contract_mid_when_set(self) -> None:
        """contract_mid appears when set."""
        ctx = _make_context(contract_mid=Decimal("4.65"))
        text = render_context_block(ctx)
        assert "CONTRACT MID: $4.65" in text

    def test_omits_contract_mid_when_none(self) -> None:
        """contract_mid does NOT appear when None."""
        ctx = _make_context()
        text = render_context_block(ctx)
        assert "CONTRACT MID" not in text

    def test_always_includes_composite_score_and_direction(self) -> None:
        """Scoring context (composite score, direction) always appears."""
        ctx = _make_context()
        text = render_context_block(ctx)
        assert "COMPOSITE SCORE: 0.0" in text
        assert "DIRECTION: neutral" in text

    def test_existing_fields_unchanged(self) -> None:
        """Original static fields remain present and unmodified."""
        ctx = _make_context()
        text = render_context_block(ctx)
        assert "TICKER: AAPL" in text
        assert "PRICE: $185.50" in text
        assert "RSI(14): 62.3" in text
        assert "EXERCISE: american" in text


# ---------------------------------------------------------------------------
# _render_optional helper
# ---------------------------------------------------------------------------


class TestRenderOptional:
    """Tests for the _render_optional helper."""

    def test_renders_valid_float(self) -> None:
        assert _render_optional("ADX", 75.0) == "ADX: 75.0"

    def test_returns_none_for_none(self) -> None:
        assert _render_optional("ADX", None) is None

    def test_returns_none_for_nan(self) -> None:
        assert _render_optional("ADX", float("nan")) is None

    def test_returns_none_for_inf(self) -> None:
        assert _render_optional("ADX", float("inf")) is None

    def test_custom_format(self) -> None:
        assert _render_optional("GAMMA", 0.025, ".4f") == "GAMMA: 0.0250"


# ---------------------------------------------------------------------------
# build_market_context — Field Population (#73)
# ---------------------------------------------------------------------------


class TestBuildMarketContextExpanded:
    """Tests for build_market_context populating the 13 new fields."""

    @pytest.fixture()
    def ticker_score(self) -> TickerScore:
        return TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(
                rsi=62.3,
                adx=28.4,
                sma_alignment=0.7,
                bb_width=42.1,
                atr_pct=15.3,
                stochastic_rsi=55.0,
                relative_volume=65.0,
            ),
            scan_run_id=1,
        )

    @pytest.fixture()
    def quote(self) -> Quote:
        return Quote(
            ticker="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.48"),
            ask=Decimal("185.52"),
            volume=42_000_000,
            timestamp=datetime(2026, 2, 25, 14, 0, 0, tzinfo=UTC),
        )

    @pytest.fixture()
    def ticker_info(self) -> TickerInfo:
        return TickerInfo(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            market_cap=2_800_000_000_000,
            dividend_yield=0.005,
            current_price=Decimal("185.50"),
            fifty_two_week_high=Decimal("199.62"),
            fifty_two_week_low=Decimal("164.08"),
        )

    @pytest.fixture()
    def contract_with_greeks(self) -> OptionContract:
        return OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("190.00"),
            expiration=(datetime.now(UTC) + timedelta(days=45)).date(),
            bid=Decimal("4.50"),
            ask=Decimal("4.80"),
            last=Decimal("4.65"),
            volume=1500,
            open_interest=12000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.285,
            greeks=OptionGreeks(
                delta=0.35,
                gamma=0.025,
                theta=-0.045,
                vega=0.32,
                rho=0.08,
                pricing_model=PricingModel.BAW,
            ),
        )

    def test_populates_scoring_context(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contract_with_greeks: OptionContract,
    ) -> None:
        """build_market_context maps composite_score and direction_signal."""
        ctx = build_market_context(ticker_score, quote, ticker_info, [contract_with_greeks])
        assert ctx.composite_score == pytest.approx(72.5)
        assert ctx.direction_signal == SignalDirection.BULLISH

    def test_populates_indicators(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contract_with_greeks: OptionContract,
    ) -> None:
        """build_market_context maps indicator signals from TickerScore."""
        ctx = build_market_context(ticker_score, quote, ticker_info, [contract_with_greeks])
        assert ctx.adx == pytest.approx(28.4)
        assert ctx.sma_alignment == pytest.approx(0.7)
        assert ctx.bb_width == pytest.approx(42.1)
        assert ctx.atr_pct == pytest.approx(15.3)
        assert ctx.stochastic_rsi == pytest.approx(55.0)
        assert ctx.relative_volume == pytest.approx(65.0)

    def test_populates_greeks_from_contract(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contract_with_greeks: OptionContract,
    ) -> None:
        """build_market_context maps gamma, theta, vega, rho from first contract."""
        ctx = build_market_context(ticker_score, quote, ticker_info, [contract_with_greeks])
        assert ctx.target_gamma == pytest.approx(0.025)
        assert ctx.target_theta == pytest.approx(-0.045)
        assert ctx.target_vega == pytest.approx(0.32)
        assert ctx.target_rho == pytest.approx(0.08)

    def test_populates_contract_mid(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
        contract_with_greeks: OptionContract,
    ) -> None:
        """build_market_context maps contract mid price from first contract."""
        ctx = build_market_context(ticker_score, quote, ticker_info, [contract_with_greeks])
        assert ctx.contract_mid == Decimal("4.65")

    def test_empty_contracts_uses_defaults(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
    ) -> None:
        """With no contracts, Greek and pricing fields remain at defaults."""
        ctx = build_market_context(ticker_score, quote, ticker_info, [])
        assert ctx.target_gamma is None
        assert ctx.target_theta is None
        assert ctx.target_vega is None
        assert ctx.target_rho is None
        assert ctx.contract_mid is None

    def test_contract_without_greeks_uses_defaults(
        self,
        ticker_score: TickerScore,
        quote: Quote,
        ticker_info: TickerInfo,
    ) -> None:
        """When first contract has greeks=None, Greek fields remain None."""
        contract_no_greeks = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("190.00"),
            expiration=(datetime.now(UTC) + timedelta(days=45)).date(),
            bid=Decimal("4.50"),
            ask=Decimal("4.80"),
            last=Decimal("4.65"),
            volume=1500,
            open_interest=12000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.285,
            greeks=None,
        )
        ctx = build_market_context(ticker_score, quote, ticker_info, [contract_no_greeks])
        assert ctx.target_gamma is None
        assert ctx.target_theta is None
        assert ctx.target_vega is None
        assert ctx.target_rho is None
        # contract_mid should still be populated (bid+ask)/2
        assert ctx.contract_mid == Decimal("4.65")


# ---------------------------------------------------------------------------
# Short Ratio in Context Block (#319)
# ---------------------------------------------------------------------------


class TestShortRatioInContext:
    """Tests for short_ratio rendering in the context block (#319)."""

    def test_context_block_renders_short_ratio(self) -> None:
        """SHORT RATIO appears in the Fundamental Profile section when set."""
        ctx = _make_context(short_ratio=3.5)
        text = render_context_block(ctx)
        assert "SHORT RATIO: 3.50" in text
        assert "Fundamental Profile" in text

    def test_context_block_omits_when_none(self) -> None:
        """SHORT RATIO does not appear when short_ratio is None."""
        ctx = _make_context(short_ratio=None)
        text = render_context_block(ctx)
        assert "SHORT RATIO" not in text
