"""Tests for complexity assessment and model routing logic."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pydantic_ai.models
import pytest

from options_arena.agents.model_routing import (
    _assess_complexity,
    build_model_for_tier,
    route_model_tier,
)
from options_arena.models import (
    DebateConfig,
    DeskType,
    ModelTier,
    RoutingConfig,
    SignalDirection,
)
from options_arena.models.analysis import MarketContext
from options_arena.models.enums import ExerciseStyle, MacdSignal
from options_arena.models.scan import IndicatorSignals, TickerScore

pydantic_ai.models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    next_earnings: date | None = None,
    rsi_14: float = 50.0,
    iv_rank: float | None = None,
    put_call_ratio: float | None = None,
) -> MarketContext:
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("190.00"),
        price_52w_high=Decimal("200.00"),
        price_52w_low=Decimal("150.00"),
        rsi_14=rsi_14,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        next_earnings=next_earnings,
        iv_rank=iv_rank,
        put_call_ratio=put_call_ratio,
        dte_target=45,
        target_strike=Decimal("195.00"),
        target_delta=0.35,
        sector="Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
    )


def _make_ticker_score(
    *,
    composite_score: float = 60.0,
    rsi: float | None = 55.0,
    iv_rank: float | None = None,
    put_call_ratio: float | None = None,
    adx: float | None = 25.0,
) -> TickerScore:
    return TickerScore(
        ticker="AAPL",
        composite_score=composite_score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=rsi,
            iv_rank=iv_rank,
            put_call_ratio=put_call_ratio,
            adx=adx,
        ),
    )


# ---------------------------------------------------------------------------
# _assess_complexity
# ---------------------------------------------------------------------------


class TestAssessComplexity:
    def test_simple_ticker_low_complexity(self) -> None:
        """Clear trend, good data, no earnings => low complexity."""
        context = _make_context()
        score = _make_ticker_score(composite_score=60.0, adx=30.0)
        result = _assess_complexity(context, score)
        assert result < 0.3

    def test_complex_ticker_high_complexity(self) -> None:
        """Earnings soon, extreme RSI, extreme IV, no trend, extreme composite."""
        context = _make_context(
            next_earnings=date.today() + timedelta(days=3),
            iv_rank=90.0,
            put_call_ratio=3.0,
        )
        score = _make_ticker_score(
            composite_score=25.0,
            rsi=85.0,
            iv_rank=90.0,
            put_call_ratio=3.0,
            adx=10.0,
        )
        result = _assess_complexity(context, score)
        assert result > 0.7

    def test_all_none_indicators(self) -> None:
        """All-None signals doesn't crash, returns low complexity."""
        context = _make_context()
        score = _make_ticker_score(
            rsi=None,
            iv_rank=None,
            put_call_ratio=None,
            adx=None,
        )
        result = _assess_complexity(context, score)
        assert 0.0 <= result <= 1.0

    def test_nan_indicators_guarded(self) -> None:
        """NaN indicator values are safely skipped (composite_score must be valid)."""
        context = _make_context()
        score = _make_ticker_score(
            rsi=float("nan"),
            iv_rank=float("nan"),
            put_call_ratio=float("nan"),
            adx=float("nan"),
            composite_score=50.0,  # composite_score has its own validator, can't be NaN
        )
        result = _assess_complexity(context, score)
        assert math.isfinite(result)

    def test_clamped_to_unit_interval(self) -> None:
        """Output is always in [0.0, 1.0] even with extreme inputs."""
        context = _make_context(
            next_earnings=date.today(),
            iv_rank=99.0,
            put_call_ratio=5.0,
        )
        score = _make_ticker_score(
            composite_score=10.0,
            rsi=95.0,
            iv_rank=99.0,
            put_call_ratio=5.0,
            adx=5.0,
        )
        result = _assess_complexity(context, score)
        assert 0.0 <= result <= 1.0

    def test_earnings_proximity_adds_complexity(self) -> None:
        """next_earnings within 7 days increases score by 0.2."""
        context_no_earnings = _make_context()
        context_earnings = _make_context(next_earnings=date.today() + timedelta(days=5))
        score = _make_ticker_score()

        base = _assess_complexity(context_no_earnings, score)
        with_earnings = _assess_complexity(context_earnings, score)
        assert with_earnings == pytest.approx(base + 0.2, abs=0.01)

    def test_no_earnings_field(self) -> None:
        """next_earnings=None is safely handled."""
        context = _make_context(next_earnings=None)
        score = _make_ticker_score()
        result = _assess_complexity(context, score)
        assert math.isfinite(result)


# ---------------------------------------------------------------------------
# route_model_tier
# ---------------------------------------------------------------------------


class TestRouteModelTier:
    def test_routing_disabled_returns_standard(self) -> None:
        """Disabled routing always returns STANDARD."""
        config = RoutingConfig(enable_model_routing=False)
        context = _make_context()
        score = _make_ticker_score()
        tier = route_model_tier(DeskType.TREND, context, score, config)
        assert tier == ModelTier.STANDARD

    def test_low_complexity_returns_fast(self) -> None:
        """Complexity < 0.3 returns FAST."""
        config = RoutingConfig(enable_model_routing=True)
        context = _make_context()
        score = _make_ticker_score(composite_score=60.0, adx=30.0)
        tier = route_model_tier(DeskType.TREND, context, score, config)
        assert tier == ModelTier.FAST

    def test_high_complexity_returns_premium(self) -> None:
        """Complexity >= 0.7 returns PREMIUM."""
        config = RoutingConfig(enable_model_routing=True)
        context = _make_context(
            next_earnings=date.today() + timedelta(days=2),
            iv_rank=90.0,
            put_call_ratio=3.0,
        )
        score = _make_ticker_score(
            composite_score=20.0,
            rsi=85.0,
            iv_rank=90.0,
            put_call_ratio=3.0,
            adx=10.0,
        )
        tier = route_model_tier(DeskType.TREND, context, score, config)
        assert tier == ModelTier.PREMIUM

    def test_mid_complexity_returns_standard(self) -> None:
        """Complexity between thresholds returns STANDARD."""
        config = RoutingConfig(enable_model_routing=True)
        # Earnings nearby adds 0.2, plus low completeness adds 0.2 = ~0.4
        context = _make_context(next_earnings=date.today() + timedelta(days=5))
        score = _make_ticker_score(composite_score=60.0, adx=25.0)
        tier = route_model_tier(DeskType.TREND, context, score, config)
        assert tier == ModelTier.STANDARD

    def test_risk_desk_never_fast(self) -> None:
        """Risk desk returns STANDARD even when complexity is low."""
        config = RoutingConfig(enable_model_routing=True)
        context = _make_context()
        score = _make_ticker_score(composite_score=60.0, adx=30.0)
        tier = route_model_tier(DeskType.RISK, context, score, config)
        assert tier != ModelTier.FAST
        assert tier in (ModelTier.STANDARD, ModelTier.PREMIUM)

    def test_custom_thresholds(self) -> None:
        """Custom threshold values are respected."""
        config = RoutingConfig(
            enable_model_routing=True,
            complexity_threshold_fast=0.1,
            complexity_threshold_premium=0.9,
        )
        context = _make_context()
        score = _make_ticker_score(composite_score=60.0, adx=30.0)
        tier = route_model_tier(DeskType.TREND, context, score, config)
        # With low complexity and threshold at 0.1, should be STANDARD or FAST
        assert tier in (ModelTier.FAST, ModelTier.STANDARD)

    def test_all_desks_get_standard_when_disabled(self) -> None:
        """Every desk type gets STANDARD when routing is off."""
        config = RoutingConfig(enable_model_routing=False)
        context = _make_context()
        score = _make_ticker_score()
        for desk in DeskType:
            if desk == DeskType.RESEARCH:
                continue  # Research desk not used in recommendations
            tier = route_model_tier(desk, context, score, config)
            assert tier == ModelTier.STANDARD


# ---------------------------------------------------------------------------
# build_model_for_tier
# ---------------------------------------------------------------------------


class TestBuildModelForTier:
    def test_standard_returns_default_model(self) -> None:
        """STANDARD tier uses config.model unchanged."""
        config = DebateConfig()
        with patch("options_arena.agents.model_routing.build_debate_model") as mock:
            mock.return_value = "mock_model"
            result = build_model_for_tier(ModelTier.STANDARD, config)
            assert result == "mock_model"
            mock.assert_called_once_with(config)

    def test_fast_returns_fast_model(self) -> None:
        """FAST tier uses config.routing.fast_model."""
        config = DebateConfig()
        with patch("options_arena.agents.model_routing.build_debate_model") as mock:
            mock.return_value = "fast_mock"
            result = build_model_for_tier(ModelTier.FAST, config)
            assert result == "fast_mock"
            call_config = mock.call_args[0][0]
            assert call_config.model == config.routing.fast_model

    def test_premium_with_override(self) -> None:
        """PREMIUM tier uses premium_model when set."""
        config = DebateConfig(routing=RoutingConfig(premium_model="llama-3.3-70b-specdec"))
        with patch("options_arena.agents.model_routing.build_debate_model") as mock:
            mock.return_value = "premium_mock"
            result = build_model_for_tier(ModelTier.PREMIUM, config)
            assert result == "premium_mock"
            call_config = mock.call_args[0][0]
            assert call_config.model == "llama-3.3-70b-specdec"

    def test_premium_without_override(self) -> None:
        """PREMIUM tier falls back to default model when premium_model is empty."""
        config = DebateConfig(routing=RoutingConfig(premium_model=""))
        with patch("options_arena.agents.model_routing.build_debate_model") as mock:
            mock.return_value = "default_mock"
            result = build_model_for_tier(ModelTier.PREMIUM, config)
            assert result == "default_mock"
            mock.assert_called_once_with(config)
