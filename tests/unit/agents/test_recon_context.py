"""Tests for 7 new intelligence + DSE sections in render_context_block().

Tests cover:
  - Analyst Intelligence section (target mean, upside %, consensus, upgrades/downgrades)
  - Insider Activity section (net buys, buy ratio)
  - Institutional Ownership section (institutional_pct as percentage)
  - Signal Dimensions section (8 dimensional scores + direction confidence)
  - Volatility Regime section (regime labels, IV-HV spread, skew, term structure, expected move)
  - Market & Flow Signals section (market regime, GEX, unusual activity, RSI divergence)
  - Second-Order Greeks section (vanna, charm, vomma)
  - Full context block ordering (new sections after OpenBB, before earnings warning)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from options_arena.agents._parsing import render_context_block
from options_arena.models import ExerciseStyle, MacdSignal, MarketContext


def _make_ctx(**overrides: object) -> MarketContext:
    """Build a MarketContext with sensible defaults, allowing field overrides."""
    defaults: dict[str, object] = {
        "ticker": "TEST",
        "current_price": Decimal("100.00"),
        "price_52w_high": Decimal("120.00"),
        "price_52w_low": Decimal("80.00"),
        "rsi_14": 50.0,
        "macd_signal": MacdSignal.NEUTRAL,
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("105.00"),
        "target_delta": 0.35,
        "sector": "Technology",
        "dividend_yield": 0.01,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 3, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Analyst Intelligence section
# ---------------------------------------------------------------------------


class TestAnalystIntelligenceSection:
    """Tests for ## Analyst Intelligence section in context block."""

    def test_all_analyst_fields_present(self) -> None:
        """Section renders with all analyst fields populated."""
        ctx = _make_ctx(
            analyst_target_mean=215.50,
            analyst_target_upside_pct=0.155,
            analyst_consensus_score=0.72,
            analyst_upgrades_30d=5,
            analyst_downgrades_30d=1,
        )
        block = render_context_block(ctx)
        assert "## Analyst Intelligence" in block
        assert "ANALYST TARGET MEAN: 215.50" in block
        assert "ANALYST TARGET UPSIDE: +15.5%" in block
        assert "ANALYST CONSENSUS: +0.72" in block
        assert "UPGRADES/DOWNGRADES (30D): 5/1" in block

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted entirely when all analyst fields are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Analyst Intelligence" not in block

    def test_partial_analyst_fields(self) -> None:
        """Only non-None analyst fields rendered."""
        ctx = _make_ctx(analyst_target_mean=150.00)
        block = render_context_block(ctx)
        assert "## Analyst Intelligence" in block
        assert "ANALYST TARGET MEAN: 150.00" in block
        assert "ANALYST TARGET UPSIDE:" not in block
        assert "ANALYST CONSENSUS:" not in block
        assert "UPGRADES/DOWNGRADES" not in block

    def test_negative_upside_pct(self) -> None:
        """Negative target upside renders with minus sign."""
        ctx = _make_ctx(analyst_target_upside_pct=-0.12)
        block = render_context_block(ctx)
        assert "ANALYST TARGET UPSIDE: -12.0%" in block

    def test_upgrades_only(self) -> None:
        """When only upgrades is set (downgrades None), downgrades defaults to 0."""
        ctx = _make_ctx(analyst_upgrades_30d=3)
        block = render_context_block(ctx)
        assert "UPGRADES/DOWNGRADES (30D): 3/0" in block

    def test_downgrades_only(self) -> None:
        """When only downgrades is set (upgrades None), upgrades defaults to 0."""
        ctx = _make_ctx(analyst_downgrades_30d=2)
        block = render_context_block(ctx)
        assert "UPGRADES/DOWNGRADES (30D): 0/2" in block


# ---------------------------------------------------------------------------
# 2. Insider Activity section
# ---------------------------------------------------------------------------


class TestInsiderActivitySection:
    """Tests for ## Insider Activity section in context block."""

    def test_all_insider_fields_present(self) -> None:
        """Section renders with both insider fields populated."""
        ctx = _make_ctx(insider_net_buys_90d=12, insider_buy_ratio=0.75)
        block = render_context_block(ctx)
        assert "## Insider Activity" in block
        assert "INSIDER NET BUYS (90D): +12" in block
        assert "INSIDER BUY RATIO: 0.75" in block

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted when both insider fields are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Insider Activity" not in block

    def test_negative_net_buys(self) -> None:
        """Negative net buys (more sells) renders with minus sign."""
        ctx = _make_ctx(insider_net_buys_90d=-5)
        block = render_context_block(ctx)
        assert "INSIDER NET BUYS (90D): -5" in block

    def test_zero_net_buys(self) -> None:
        """Zero net buys renders with plus sign (+0)."""
        ctx = _make_ctx(insider_net_buys_90d=0)
        block = render_context_block(ctx)
        assert "INSIDER NET BUYS (90D): +0" in block


# ---------------------------------------------------------------------------
# 3. Institutional Ownership section
# ---------------------------------------------------------------------------


class TestInstitutionalSection:
    """Tests for ## Institutional Ownership section in context block."""

    def test_institutional_pct_present(self) -> None:
        """Section renders institutional ownership as percentage."""
        ctx = _make_ctx(institutional_pct=0.742)
        block = render_context_block(ctx)
        assert "## Institutional Ownership" in block
        assert "INSTITUTIONAL OWNERSHIP: 74.2%" in block

    def test_section_omitted_when_none(self) -> None:
        """Section omitted when institutional_pct is None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Institutional Ownership" not in block

    def test_high_institutional_pct(self) -> None:
        """100% institutional ownership renders correctly."""
        ctx = _make_ctx(institutional_pct=1.0)
        block = render_context_block(ctx)
        assert "INSTITUTIONAL OWNERSHIP: 100.0%" in block


# ---------------------------------------------------------------------------
# 4. Signal Dimensions section
# ---------------------------------------------------------------------------


class TestSignalDimensionsSection:
    """Tests for ## Signal Dimensions (0-100) section in context block."""

    def test_all_dimensions_present(self) -> None:
        """Section renders with all 8 dimensional scores + direction confidence."""
        ctx = _make_ctx(
            dim_trend=72.5,
            dim_iv_vol=45.0,
            dim_hv_vol=38.2,
            dim_flow=60.1,
            dim_microstructure=55.0,
            dim_fundamental=48.3,
            dim_regime=65.0,
            dim_risk=30.5,
            direction_confidence=0.82,
        )
        block = render_context_block(ctx)
        assert "## Signal Dimensions (0-100)" in block
        assert "TREND: 72.5" in block
        assert "IV VOLATILITY: 45.0" in block
        assert "HV VOLATILITY: 38.2" in block
        assert "FLOW: 60.1" in block
        assert "MICROSTRUCTURE: 55.0" in block
        assert "FUNDAMENTAL: 48.3" in block
        assert "REGIME: 65.0" in block
        assert "RISK: 30.5" in block
        assert "DIRECTION CONFIDENCE: 0.82" in block

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted when all dimensional scores are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Signal Dimensions (0-100)" not in block

    def test_partial_dimensions(self) -> None:
        """Only non-None dimensions rendered."""
        ctx = _make_ctx(dim_trend=72.5, dim_risk=30.5)
        block = render_context_block(ctx)
        assert "## Signal Dimensions (0-100)" in block
        assert "TREND: 72.5" in block
        assert "RISK: 30.5" in block
        assert "IV VOLATILITY:" not in block
        assert "FLOW:" not in block

    def test_direction_confidence_alone(self) -> None:
        """direction_confidence alone triggers section."""
        ctx = _make_ctx(direction_confidence=0.65)
        block = render_context_block(ctx)
        assert "## Signal Dimensions (0-100)" in block
        assert "DIRECTION CONFIDENCE: 0.65" in block


# ---------------------------------------------------------------------------
# 5. Volatility Regime section
# ---------------------------------------------------------------------------


class TestVolatilityRegimeSection:
    """Tests for ## Volatility Regime section in context block."""

    def test_all_vol_regime_fields(self) -> None:
        """Section renders with all volatility regime fields."""
        ctx = _make_ctx(
            vol_regime=1.0,
            iv_hv_spread=5.25,
            skew_ratio=1.15,
            vix_term_structure=0.95,
            expected_move=8.50,
            expected_move_ratio=0.042,
        )
        block = render_context_block(ctx)
        assert "## Volatility Regime" in block
        assert "VOL REGIME: ELEVATED" in block
        assert "IV-HV SPREAD: 5.25" in block
        assert "SKEW RATIO: 1.15" in block
        assert "VIX TERM STRUCTURE: 0.95" in block
        assert "EXPECTED MOVE ($): 8.50" in block
        assert "EXPECTED MOVE RATIO: 0.04" in block  # .2f format

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted when all vol regime fields are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Volatility Regime" not in block

    def test_vol_regime_labels(self) -> None:
        """Vol regime numeric values map to human-readable labels."""
        for value, label in [(0.0, "NORMAL"), (1.0, "ELEVATED"), (2.0, "CRISIS")]:
            ctx = _make_ctx(vol_regime=value)
            block = render_context_block(ctx)
            assert f"VOL REGIME: {label}" in block

    def test_vol_regime_unknown_value(self) -> None:
        """Unknown vol_regime value falls back to numeric display."""
        ctx = _make_ctx(vol_regime=5.0)
        block = render_context_block(ctx)
        assert "VOL REGIME: 5" in block


# ---------------------------------------------------------------------------
# 6. Market & Flow Signals section
# ---------------------------------------------------------------------------


class TestMarketFlowSection:
    """Tests for ## Market & Flow Signals section in context block."""

    def test_all_market_fields(self) -> None:
        """Section renders with all market/flow fields."""
        ctx = _make_ctx(
            market_regime=2.0,
            gex=1_500_000.0,
            unusual_activity_score=78.5,
            rsi_divergence=-0.35,
        )
        block = render_context_block(ctx)
        assert "## Market & Flow Signals" in block
        assert "MARKET REGIME: TRENDING" in block
        assert "GEX: 1,500,000" in block
        assert "UNUSUAL ACTIVITY SCORE: 78.5" in block
        assert "RSI DIVERGENCE: -0.35" in block

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted when all market/flow fields are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Market & Flow Signals" not in block

    def test_market_regime_labels(self) -> None:
        """Market regime numeric values map to human-readable labels."""
        for value, label in [
            (0.0, "CRISIS"),
            (1.0, "VOLATILE"),
            (2.0, "TRENDING"),
            (3.0, "MEAN_REVERTING"),
        ]:
            ctx = _make_ctx(market_regime=value)
            block = render_context_block(ctx)
            assert f"MARKET REGIME: {label}" in block

    def test_partial_market_fields(self) -> None:
        """Only non-None market/flow fields rendered."""
        ctx = _make_ctx(gex=-500_000.0)
        block = render_context_block(ctx)
        assert "## Market & Flow Signals" in block
        assert "GEX: -500,000" in block
        assert "MARKET REGIME:" not in block
        assert "UNUSUAL ACTIVITY SCORE:" not in block


# ---------------------------------------------------------------------------
# 7. Second-Order Greeks section
# ---------------------------------------------------------------------------


class TestSecondOrderGreeksSection:
    """Tests for ## Second-Order Greeks section in context block."""

    def test_all_second_order_greeks(self) -> None:
        """Section renders with all 3 second-order Greeks."""
        ctx = _make_ctx(
            target_vanna=0.002345,
            target_charm=-0.001234,
            target_vomma=0.000567,
        )
        block = render_context_block(ctx)
        assert "## Second-Order Greeks" in block
        assert "VANNA: 0.002345" in block
        assert "CHARM: -0.001234" in block
        assert "VOMMA: 0.000567" in block

    def test_section_omitted_when_all_none(self) -> None:
        """Section omitted when all second-order Greeks are None."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Second-Order Greeks" not in block

    def test_partial_second_order_greeks(self) -> None:
        """Only non-None second-order Greeks rendered."""
        ctx = _make_ctx(target_vanna=0.001500)
        block = render_context_block(ctx)
        assert "## Second-Order Greeks" in block
        assert "VANNA: 0.001500" in block
        assert "CHARM:" not in block
        assert "VOMMA:" not in block


# ---------------------------------------------------------------------------
# Full context block ordering and integration
# ---------------------------------------------------------------------------


class TestFullContextBlock:
    """Tests for ordering and interaction of all 7 new sections."""

    def test_new_sections_appear_after_openbb(self) -> None:
        """New sections appear after News Sentiment section."""
        ctx = _make_ctx(
            news_sentiment=0.42,
            news_sentiment_label="bullish",
            analyst_target_mean=215.50,
            dim_trend=72.5,
        )
        block = render_context_block(ctx)
        # News Sentiment should come before Analyst Intelligence
        sentiment_pos = block.index("## News Sentiment")
        analyst_pos = block.index("## Analyst Intelligence")
        dim_pos = block.index("## Signal Dimensions (0-100)")
        assert sentiment_pos < analyst_pos
        assert analyst_pos < dim_pos

    def test_new_sections_appear_before_earnings_warning(self) -> None:
        """New sections appear before the earnings warning."""
        # Set next_earnings to tomorrow to trigger warning
        tomorrow = date.today() + timedelta(days=1)
        ctx = _make_ctx(
            next_earnings=tomorrow,
            dim_trend=72.5,
            target_vanna=0.001,
        )
        block = render_context_block(ctx)
        dim_pos = block.index("## Signal Dimensions (0-100)")
        greeks_pos = block.index("## Second-Order Greeks")
        earnings_pos = block.index("NEXT EARNINGS:")
        assert dim_pos < earnings_pos
        assert greeks_pos < earnings_pos

    def test_all_seven_sections_present(self) -> None:
        """All 7 new sections rendered when all fields populated."""
        ctx = _make_ctx(
            # Analyst Intelligence
            analyst_target_mean=215.50,
            analyst_target_upside_pct=0.155,
            analyst_consensus_score=0.72,
            analyst_upgrades_30d=5,
            analyst_downgrades_30d=1,
            # Insider Activity
            insider_net_buys_90d=12,
            insider_buy_ratio=0.75,
            # Institutional Ownership
            institutional_pct=0.742,
            # Signal Dimensions
            dim_trend=72.5,
            dim_iv_vol=45.0,
            dim_hv_vol=38.2,
            dim_flow=60.1,
            dim_microstructure=55.0,
            dim_fundamental=48.3,
            dim_regime=65.0,
            dim_risk=30.5,
            direction_confidence=0.82,
            # Volatility Regime
            vol_regime=1.0,
            iv_hv_spread=5.25,
            skew_ratio=1.15,
            vix_term_structure=0.95,
            expected_move=8.50,
            expected_move_ratio=0.042,
            # Market & Flow Signals
            market_regime=2.0,
            gex=1_500_000.0,
            unusual_activity_score=78.5,
            rsi_divergence=-0.35,
            # Second-Order Greeks
            target_vanna=0.002345,
            target_charm=-0.001234,
            target_vomma=0.000567,
        )
        block = render_context_block(ctx)
        assert "## Analyst Intelligence" in block
        assert "## Insider Activity" in block
        assert "## Institutional Ownership" in block
        assert "## Signal Dimensions (0-100)" in block
        assert "## Volatility Regime" in block
        assert "## Market & Flow Signals" in block
        assert "## Second-Order Greeks" in block

    def test_section_ordering(self) -> None:
        """Sections appear in the correct order."""
        ctx = _make_ctx(
            analyst_target_mean=215.50,
            insider_net_buys_90d=12,
            institutional_pct=0.742,
            dim_trend=72.5,
            vol_regime=1.0,
            market_regime=2.0,
            target_vanna=0.001,
        )
        block = render_context_block(ctx)
        positions = [
            block.index("## Analyst Intelligence"),
            block.index("## Insider Activity"),
            block.index("## Institutional Ownership"),
            block.index("## Signal Dimensions (0-100)"),
            block.index("## Volatility Regime"),
            block.index("## Market & Flow Signals"),
            block.index("## Second-Order Greeks"),
        ]
        assert positions == sorted(positions), "Sections are not in correct order"

    def test_no_new_sections_by_default(self) -> None:
        """No new sections appear when all new fields are None (backward compat)."""
        ctx = _make_ctx()
        block = render_context_block(ctx)
        assert "## Analyst Intelligence" not in block
        assert "## Insider Activity" not in block
        assert "## Institutional Ownership" not in block
        assert "## Signal Dimensions (0-100)" not in block
        assert "## Volatility Regime" not in block
        assert "## Market & Flow Signals" not in block
        assert "## Second-Order Greeks" not in block

    def test_existing_sections_unaffected(self) -> None:
        """Existing core fields still render correctly with new sections present."""
        ctx = _make_ctx(
            analyst_target_mean=215.50,
            dim_trend=72.5,
        )
        block = render_context_block(ctx)
        assert "TICKER: TEST" in block
        assert "PRICE: $100.00" in block
        assert "RSI(14): 50.0" in block
        assert "EXERCISE: american" in block
