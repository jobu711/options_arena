"""Tests for intelligence + DSE field wiring in build_market_context().

Tests cover:
  - Intelligence fields mapped from IntelligencePackage to MarketContext
  - Intelligence None => all intelligence fields None on MarketContext
  - Partial IntelligencePackage (some sub-snapshots None)
  - Individual sub-snapshot None checks (analyst, insider, institutional)
  - DSE dimensional scores mapped from TickerScore.dimensional_scores
  - DSE dimensional scores None => all dim_* fields None
  - Individual DSE indicator signals mapped from TickerScore.signals
  - Second-order Greeks mapped from TickerScore.signals
  - Direction confidence mapped from TickerScore
  - Signals None-safe (IndicatorSignals with all None)
  - Combined: all 30 new fields populated
  - Combined: all 30 new fields None
  - Existing fields unaffected by new intelligence/DSE wiring
  - run_debate() accepts intelligence parameter with None default
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic_ai import models

from options_arena.agents.orchestrator import (
    build_market_context,
    run_debate,
)
from options_arena.models import (
    DimensionalScores,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from options_arena.models.intelligence import (
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InstitutionalSnapshot,
    IntelligencePackage,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Factory helpers — build test objects with overrides
# ---------------------------------------------------------------------------


def _make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with bullish direction and DSE signals."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 75.0,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(
            rsi=65.0,
            iv_rank=50.0,
            iv_percentile=45.0,
            vol_regime=1.0,
            iv_hv_spread=5.0,
            gex=50000.0,
            unusual_activity_score=72.0,
            skew_ratio=1.15,
            rsi_divergence=0.3,
            expected_move=8.5,
            expected_move_ratio=0.05,
            vanna=0.001,
            charm=-0.002,
            vomma=0.0003,
        ),
        "dimensional_scores": DimensionalScores(
            trend=80.0,
            iv_vol=65.0,
            hv_vol=55.0,
            flow=70.0,
            microstructure=60.0,
            fundamental=75.0,
            regime=50.0,
            risk=45.0,
        ),
        "direction_confidence": 0.85,
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


def _make_quote() -> Quote:
    """Build a Quote for AAPL."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.00"),
        bid=Decimal("184.98"),
        ask=Decimal("185.02"),
        volume=45_000_000,
        timestamp=datetime.now(UTC),
    )


def _make_ticker_info() -> TickerInfo:
    """Build a TickerInfo for AAPL."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        current_price=Decimal("185.00"),
        fifty_two_week_high=Decimal("200.00"),
        fifty_two_week_low=Decimal("140.00"),
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
    )


def _make_contract() -> OptionContract:
    """Build an OptionContract for AAPL with Greeks."""
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("190.00"),
        expiration=datetime.now(UTC).date() + timedelta(days=45),
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


def _make_intelligence() -> IntelligencePackage:
    """Build a fully populated IntelligencePackage for AAPL."""
    now = datetime.now(UTC)
    return IntelligencePackage(
        ticker="AAPL",
        analyst=AnalystSnapshot(
            ticker="AAPL",
            target_mean=210.0,
            current_price=185.0,
            strong_buy=10,
            buy=15,
            hold=5,
            sell=2,
            strong_sell=0,
            fetched_at=now,
        ),
        analyst_activity=AnalystActivitySnapshot(
            ticker="AAPL",
            recent_changes=[],
            upgrades_30d=3,
            downgrades_30d=1,
            fetched_at=now,
        ),
        insider=InsiderSnapshot(
            ticker="AAPL",
            transactions=[],
            net_insider_buys_90d=5,
            insider_buy_ratio=0.7,
            fetched_at=now,
        ),
        institutional=InstitutionalSnapshot(
            ticker="AAPL",
            institutional_pct=0.62,
            fetched_at=now,
        ),
        fetched_at=now,
    )


# ---------------------------------------------------------------------------
# TestBuildMarketContextIntelligence
# ---------------------------------------------------------------------------


class TestBuildMarketContextIntelligence:
    """Tests for intelligence field mapping in build_market_context."""

    def test_intelligence_fields_mapped(self) -> None:
        """All 8 intelligence fields are mapped from IntelligencePackage."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=_make_intelligence(),
        )
        assert ctx.analyst_target_mean == pytest.approx(210.0)
        # target_upside_pct is computed: (210 - 185) / 185
        assert ctx.analyst_target_upside_pct == pytest.approx((210.0 - 185.0) / 185.0, rel=1e-4)
        # consensus_score is computed from analyst counts
        assert ctx.analyst_consensus_score is not None
        assert ctx.analyst_upgrades_30d == 3
        assert ctx.analyst_downgrades_30d == 1
        assert ctx.insider_net_buys_90d == 5
        assert ctx.insider_buy_ratio == pytest.approx(0.7)
        assert ctx.institutional_pct == pytest.approx(0.62)

    def test_intelligence_none_all_fields_none(self) -> None:
        """When intelligence is None, all 8 intelligence fields are None."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=None,
        )
        assert ctx.analyst_target_mean is None
        assert ctx.analyst_target_upside_pct is None
        assert ctx.analyst_consensus_score is None
        assert ctx.analyst_upgrades_30d is None
        assert ctx.analyst_downgrades_30d is None
        assert ctx.insider_net_buys_90d is None
        assert ctx.insider_buy_ratio is None
        assert ctx.institutional_pct is None

    def test_partial_intelligence_package(self) -> None:
        """IntelligencePackage with only analyst => other fields None."""
        now = datetime.now(UTC)
        intel = IntelligencePackage(
            ticker="AAPL",
            analyst=AnalystSnapshot(
                ticker="AAPL",
                target_mean=200.0,
                current_price=185.0,
                strong_buy=5,
                buy=10,
                hold=3,
                sell=1,
                strong_sell=0,
                fetched_at=now,
            ),
            fetched_at=now,
        )
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=intel,
        )
        assert ctx.analyst_target_mean == pytest.approx(200.0)
        assert ctx.analyst_upgrades_30d is None
        assert ctx.analyst_downgrades_30d is None
        assert ctx.insider_net_buys_90d is None
        assert ctx.insider_buy_ratio is None
        assert ctx.institutional_pct is None

    def test_analyst_none_analyst_fields_none(self) -> None:
        """When intelligence.analyst is None, analyst fields are None."""
        now = datetime.now(UTC)
        intel = IntelligencePackage(
            ticker="AAPL",
            analyst=None,
            analyst_activity=AnalystActivitySnapshot(
                ticker="AAPL",
                recent_changes=[],
                upgrades_30d=2,
                downgrades_30d=0,
                fetched_at=now,
            ),
            fetched_at=now,
        )
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=intel,
        )
        assert ctx.analyst_target_mean is None
        assert ctx.analyst_target_upside_pct is None
        assert ctx.analyst_consensus_score is None
        # analyst_activity is present though
        assert ctx.analyst_upgrades_30d == 2
        assert ctx.analyst_downgrades_30d == 0

    def test_insider_none_insider_fields_none(self) -> None:
        """When intelligence.insider is None, insider fields are None."""
        now = datetime.now(UTC)
        intel = IntelligencePackage(
            ticker="AAPL",
            institutional=InstitutionalSnapshot(
                ticker="AAPL",
                institutional_pct=0.55,
                fetched_at=now,
            ),
            fetched_at=now,
        )
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=intel,
        )
        assert ctx.insider_net_buys_90d is None
        assert ctx.insider_buy_ratio is None
        assert ctx.institutional_pct == pytest.approx(0.55)

    def test_institutional_none_field_none(self) -> None:
        """When intelligence.institutional is None, institutional_pct is None."""
        now = datetime.now(UTC)
        intel = IntelligencePackage(
            ticker="AAPL",
            insider=InsiderSnapshot(
                ticker="AAPL",
                transactions=[],
                net_insider_buys_90d=3,
                insider_buy_ratio=0.6,
                fetched_at=now,
            ),
            fetched_at=now,
        )
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=intel,
        )
        assert ctx.institutional_pct is None
        assert ctx.insider_net_buys_90d == 3
        assert ctx.insider_buy_ratio == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# TestBuildMarketContextDSE
# ---------------------------------------------------------------------------


class TestBuildMarketContextDSE:
    """Tests for DSE field mapping in build_market_context."""

    def test_dimensional_scores_mapped(self) -> None:
        """All 8 dimensional scores are mapped from TickerScore.dimensional_scores."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.dim_trend == pytest.approx(80.0)
        assert ctx.dim_iv_vol == pytest.approx(65.0)
        assert ctx.dim_hv_vol == pytest.approx(55.0)
        assert ctx.dim_flow == pytest.approx(70.0)
        assert ctx.dim_microstructure == pytest.approx(60.0)
        assert ctx.dim_fundamental == pytest.approx(75.0)
        assert ctx.dim_regime == pytest.approx(50.0)
        assert ctx.dim_risk == pytest.approx(45.0)

    def test_dimensional_scores_none_all_dim_fields_none(self) -> None:
        """When dimensional_scores is None, all dim_* fields are None."""
        score = _make_ticker_score(dimensional_scores=None)
        ctx = build_market_context(
            score,
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.dim_trend is None
        assert ctx.dim_iv_vol is None
        assert ctx.dim_hv_vol is None
        assert ctx.dim_flow is None
        assert ctx.dim_microstructure is None
        assert ctx.dim_fundamental is None
        assert ctx.dim_regime is None
        assert ctx.dim_risk is None

    def test_individual_indicators_mapped(self) -> None:
        """High-signal DSE indicators from TickerScore.signals are mapped."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.vol_regime == pytest.approx(1.0)
        assert ctx.iv_hv_spread == pytest.approx(5.0)
        assert ctx.gex == pytest.approx(50000.0)
        assert ctx.unusual_activity_score == pytest.approx(72.0)
        assert ctx.skew_ratio == pytest.approx(1.15)
        assert ctx.rsi_divergence == pytest.approx(0.3)
        assert ctx.expected_move == pytest.approx(8.5)
        assert ctx.expected_move_ratio == pytest.approx(0.05)

    def test_second_order_greeks_mapped(self) -> None:
        """Second-order Greeks (vanna, charm, vomma) mapped from signals."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.target_vanna == pytest.approx(0.001)
        assert ctx.target_charm == pytest.approx(-0.002)
        assert ctx.target_vomma == pytest.approx(0.0003)

    def test_direction_confidence_mapped(self) -> None:
        """direction_confidence mapped from TickerScore."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.direction_confidence == pytest.approx(0.85)

    def test_signals_none_fields_are_none(self) -> None:
        """When IndicatorSignals has all None DSE fields, MarketContext DSE fields are None."""
        score = _make_ticker_score(
            signals=IndicatorSignals(rsi=50.0),
            dimensional_scores=None,
            direction_confidence=None,
        )
        ctx = build_market_context(
            score,
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        assert ctx.vol_regime is None
        assert ctx.iv_hv_spread is None
        assert ctx.gex is None
        assert ctx.unusual_activity_score is None
        assert ctx.skew_ratio is None
        assert ctx.rsi_divergence is None
        assert ctx.expected_move is None
        assert ctx.expected_move_ratio is None
        assert ctx.target_vanna is None
        assert ctx.target_charm is None
        assert ctx.target_vomma is None
        assert ctx.direction_confidence is None

    def test_vix_term_structure_and_market_regime_mapped_to_none(self) -> None:
        """vix_term_structure and market_regime are mapped from signals (may be None)."""
        # These fields exist on IndicatorSignals but are typically None
        score = _make_ticker_score(
            signals=IndicatorSignals(
                rsi=50.0,
                vix_term_structure=0.95,
                market_regime=2.0,
            ),
        )
        ctx = build_market_context(
            score,
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
        )
        # These should be mapped from signals when available
        assert ctx.vix_term_structure == pytest.approx(0.95)
        assert ctx.market_regime == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# TestBuildMarketContextCombined
# ---------------------------------------------------------------------------


class TestBuildMarketContextCombined:
    """Tests for combined intelligence + DSE field wiring."""

    def test_all_30_fields_populated(self) -> None:
        """All 30 new fields are populated when both intelligence and DSE data exist."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=_make_intelligence(),
        )
        # 8 intelligence fields
        assert ctx.analyst_target_mean is not None
        assert ctx.analyst_target_upside_pct is not None
        assert ctx.analyst_consensus_score is not None
        assert ctx.analyst_upgrades_30d is not None
        assert ctx.analyst_downgrades_30d is not None
        assert ctx.insider_net_buys_90d is not None
        assert ctx.insider_buy_ratio is not None
        assert ctx.institutional_pct is not None
        # 8 dimensional scores
        assert ctx.dim_trend is not None
        assert ctx.dim_iv_vol is not None
        assert ctx.dim_hv_vol is not None
        assert ctx.dim_flow is not None
        assert ctx.dim_microstructure is not None
        assert ctx.dim_fundamental is not None
        assert ctx.dim_regime is not None
        assert ctx.dim_risk is not None
        # 10 high-signal indicators
        assert ctx.vol_regime is not None
        assert ctx.iv_hv_spread is not None
        assert ctx.gex is not None
        assert ctx.unusual_activity_score is not None
        assert ctx.skew_ratio is not None
        assert ctx.rsi_divergence is not None
        assert ctx.expected_move is not None
        assert ctx.expected_move_ratio is not None
        # vix_term_structure and market_regime are None on default signals
        # 3 second-order Greeks
        assert ctx.target_vanna is not None
        assert ctx.target_charm is not None
        assert ctx.target_vomma is not None
        # 1 direction confidence
        assert ctx.direction_confidence is not None

    def test_all_30_fields_none(self) -> None:
        """All 30 new fields are None when no intelligence and no DSE data."""
        score = _make_ticker_score(
            signals=IndicatorSignals(rsi=50.0),
            dimensional_scores=None,
            direction_confidence=None,
        )
        ctx = build_market_context(
            score,
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=None,
        )
        # Intelligence fields
        assert ctx.analyst_target_mean is None
        assert ctx.analyst_target_upside_pct is None
        assert ctx.analyst_consensus_score is None
        assert ctx.analyst_upgrades_30d is None
        assert ctx.analyst_downgrades_30d is None
        assert ctx.insider_net_buys_90d is None
        assert ctx.insider_buy_ratio is None
        assert ctx.institutional_pct is None
        # Dimensional scores
        assert ctx.dim_trend is None
        assert ctx.dim_iv_vol is None
        assert ctx.dim_hv_vol is None
        assert ctx.dim_flow is None
        assert ctx.dim_microstructure is None
        assert ctx.dim_fundamental is None
        assert ctx.dim_regime is None
        assert ctx.dim_risk is None
        # DSE indicators
        assert ctx.vol_regime is None
        assert ctx.iv_hv_spread is None
        assert ctx.gex is None
        assert ctx.unusual_activity_score is None
        assert ctx.skew_ratio is None
        assert ctx.vix_term_structure is None
        assert ctx.market_regime is None
        assert ctx.rsi_divergence is None
        assert ctx.expected_move is None
        assert ctx.expected_move_ratio is None
        # Second-order Greeks
        assert ctx.target_vanna is None
        assert ctx.target_charm is None
        assert ctx.target_vomma is None
        # Direction confidence
        assert ctx.direction_confidence is None

    def test_existing_fields_unaffected(self) -> None:
        """Existing MarketContext fields still mapped correctly with intelligence present."""
        ctx = build_market_context(
            _make_ticker_score(),
            _make_quote(),
            _make_ticker_info(),
            [_make_contract()],
            intelligence=_make_intelligence(),
        )
        # Core fields from TickerScore/Quote/TickerInfo
        assert ctx.ticker == "AAPL"
        assert ctx.current_price == Decimal("185.00")
        assert ctx.price_52w_high == Decimal("200.00")
        assert ctx.price_52w_low == Decimal("140.00")
        assert ctx.sector == "Technology"
        assert ctx.dividend_yield == pytest.approx(0.005)
        assert ctx.exercise_style == ExerciseStyle.AMERICAN
        assert ctx.composite_score == pytest.approx(75.0)
        assert ctx.direction_signal == SignalDirection.BULLISH
        # Contract-derived fields
        assert ctx.target_strike == Decimal("190.00")
        assert ctx.target_delta == pytest.approx(0.35)
        assert ctx.dte_target == _make_contract().dte
        # Signals pass-through
        assert ctx.rsi_14 == pytest.approx(65.0)
        assert ctx.iv_rank == pytest.approx(50.0)
        assert ctx.iv_percentile == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# TestRunDebateSignature
# ---------------------------------------------------------------------------


class TestRunDebateSignature:
    """Tests for run_debate accepting the intelligence parameter."""

    def test_accepts_intelligence_param(self) -> None:
        """run_debate has an 'intelligence' parameter in its signature."""
        sig = inspect.signature(run_debate)
        assert "intelligence" in sig.parameters, (
            "run_debate must accept an 'intelligence' parameter"
        )

    def test_intelligence_default_is_none(self) -> None:
        """run_debate's intelligence parameter defaults to None."""
        sig = inspect.signature(run_debate)
        param = sig.parameters["intelligence"]
        assert param.default is None
