"""Tests for domain-partitioned context renderers.

Verifies that each domain renderer produces the correct domain-specific fields,
includes the shared identity block, and excludes scan-conclusion fields
(COMPOSITE SCORE, DIRECTION, DIRECTION CONFIDENCE) that cause agent correlation.

Also verifies that PROMPT_RULES_APPENDIX no longer references COMPOSITE SCORE
and includes domain-neutral calibration language.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX,
    _format_dollars,
    _render_identity_block,
    render_context_block,
    render_flow_context,
    render_fundamental_context,
    render_trend_context,
    render_volatility_context,
)
from options_arena.models import (
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    SignalDirection,
)
from options_arena.models.enums import SentimentLabel


def _make_context(**overrides: object) -> MarketContext:
    """Build a MarketContext with sensible defaults, accepting field overrides."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.50"),
        "price_52w_high": Decimal("199.62"),
        "price_52w_low": Decimal("164.08"),
        "iv_rank": 45.2,
        "iv_percentile": 52.1,
        "atm_iv_30d": 28.5,
        "rsi_14": 62.3,
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "put_call_ratio": 0.85,
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("190.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 3, 7, 14, 30, 0, tzinfo=UTC),
        "composite_score": 72.5,
        "direction_signal": SignalDirection.BULLISH,
    }
    defaults.update(overrides)
    return MarketContext(**defaults)


# ---------------------------------------------------------------------------
# _render_identity_block
# ---------------------------------------------------------------------------


class TestRenderIdentityBlock:
    """Tests for the shared identity block used by all domain renderers."""

    def test_includes_ticker_price_range(self) -> None:
        """Verify shared identity block has ticker, price, 52w range."""
        ctx = _make_context()
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "TICKER: AAPL" in text
        assert "PRICE: $185.50" in text
        assert "52W HIGH: $199.62" in text
        assert "52W LOW: $164.08" in text

    def test_includes_dte_strike_delta(self) -> None:
        """Verify shared identity includes DTE, strike, delta."""
        ctx = _make_context()
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "DTE: 45" in text
        assert "TARGET STRIKE: $190.00" in text
        assert "TARGET DELTA: 0.35" in text

    def test_includes_sector_exercise_dividend(self) -> None:
        """Verify shared identity includes sector, exercise style, div yield."""
        ctx = _make_context()
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "SECTOR: Information Technology" in text
        assert "EXERCISE: american" in text
        assert "DIV YIELD: 0.50%" in text

    def test_earnings_warning_within_7_days(self) -> None:
        """Verify earnings warning when <= 7 days away."""
        earnings_date = date.today() + timedelta(days=5)
        ctx = _make_context(next_earnings=earnings_date)
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "NEXT EARNINGS:" in text
        assert "WARNING: Earnings in 5 days" in text
        assert "IV crush risk" in text

    def test_earnings_exactly_7_days(self) -> None:
        """Verify earnings warning when exactly 7 days away."""
        earnings_date = date.today() + timedelta(days=7)
        ctx = _make_context(next_earnings=earnings_date)
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "NEXT EARNINGS:" in text
        assert "WARNING: Earnings in 7 days" in text

    def test_earnings_no_warning_beyond_7_days(self) -> None:
        """Verify no warning when earnings > 7 days away."""
        earnings_date = date.today() + timedelta(days=14)
        ctx = _make_context(next_earnings=earnings_date)
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "NEXT EARNINGS:" in text
        assert "WARNING:" not in text

    def test_no_earnings(self) -> None:
        """Verify no earnings lines when next_earnings is None."""
        ctx = _make_context(next_earnings=None)
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "NEXT EARNINGS:" not in text
        assert "WARNING:" not in text

    def test_excludes_composite_score(self) -> None:
        """Identity block must never contain scan conclusions."""
        ctx = _make_context(composite_score=85.0)
        lines = _render_identity_block(ctx)
        text = "\n".join(lines)

        assert "COMPOSITE SCORE" not in text
        assert "DIRECTION" not in text


# ---------------------------------------------------------------------------
# render_trend_context
# ---------------------------------------------------------------------------


class TestRenderTrendContext:
    """Tests for the Trend agent's domain-specific renderer."""

    def test_includes_trend_indicators(self) -> None:
        """Verify RSI, MACD, ADX, SMA alignment, stochastic RSI present."""
        ctx = _make_context(
            adx=28.4,
            sma_alignment=0.7,
            stochastic_rsi=45.5,
            relative_volume=1.3,
            rsi_divergence=1.5,
            dim_trend=65.0,
        )
        text = render_trend_context(ctx)

        assert "RSI(14): 62.3" in text
        assert "MACD: bullish_crossover" in text
        assert "ADX: 28.4" in text
        assert "SMA ALIGNMENT: 0.7" in text
        assert "STOCHASTIC RSI: 45.5" in text
        assert "REL VOLUME: 1.3" in text
        assert "RSI DIVERGENCE: 1.5" in text
        assert "TREND: 65.0" in text

    def test_excludes_composite_score(self) -> None:
        """Verify COMPOSITE SCORE not in trend context."""
        ctx = _make_context(composite_score=85.0)
        text = render_trend_context(ctx)

        assert "COMPOSITE SCORE" not in text

    def test_excludes_direction(self) -> None:
        """Verify DIRECTION not in trend context."""
        ctx = _make_context(direction_signal=SignalDirection.BULLISH)
        text = render_trend_context(ctx)

        assert "DIRECTION:" not in text
        assert "DIRECTION CONFIDENCE" not in text

    def test_handles_none_fields(self) -> None:
        """Verify None fields are omitted gracefully."""
        ctx = _make_context(
            adx=None,
            sma_alignment=None,
            stochastic_rsi=None,
            relative_volume=None,
            rsi_divergence=None,
            dim_trend=None,
        )
        text = render_trend_context(ctx)

        # Identity block always present
        assert "TICKER: AAPL" in text
        # RSI and MACD always present (have defaults / required)
        assert "RSI(14):" in text
        assert "MACD:" in text
        # Optional fields omitted
        assert "ADX:" not in text
        assert "SMA ALIGNMENT:" not in text
        assert "STOCHASTIC RSI:" not in text
        assert "RSI DIVERGENCE:" not in text
        assert "Signal Dimension" not in text

    def test_none_optional_fields_omitted(self) -> None:
        """Verify None optional fields are omitted from trend context.

        Note: MarketContext validators reject NaN/Inf values at construction
        time, so NaN/Inf never reaches the renderer. The _render_optional()
        guard handles NaN/Inf as a defense-in-depth measure.
        """
        ctx = _make_context(
            adx=None,
            sma_alignment=None,
            rsi_divergence=None,
        )
        text = render_trend_context(ctx)

        assert "ADX:" not in text
        assert "SMA ALIGNMENT:" not in text
        assert "RSI DIVERGENCE:" not in text

    def test_includes_identity_block(self) -> None:
        """Verify the identity block is present in trend context."""
        ctx = _make_context()
        text = render_trend_context(ctx)

        assert "TICKER: AAPL" in text
        assert "PRICE: $185.50" in text
        assert "SECTOR: Information Technology" in text

    def test_excludes_vol_indicators(self) -> None:
        """Verify volatility indicators are not in trend context."""
        ctx = _make_context(
            iv_rank=85.0,
            iv_percentile=90.0,
            atm_iv_30d=35.0,
        )
        text = render_trend_context(ctx)

        assert "IV RANK" not in text
        assert "IV PERCENTILE" not in text
        assert "ATM IV 30D" not in text


# ---------------------------------------------------------------------------
# render_volatility_context
# ---------------------------------------------------------------------------


class TestRenderVolatilityContext:
    """Tests for the Volatility agent's domain-specific renderer."""

    def test_includes_vol_indicators(self) -> None:
        """Verify IV rank, ATM IV, BB width, ATR% present."""
        ctx = _make_context(
            iv_rank=85.0,
            iv_percentile=90.0,
            atm_iv_30d=35.0,
            bb_width=42.0,
            atr_pct=15.3,
            vol_regime=1.0,
            iv_hv_spread=5.2,
            skew_ratio=1.15,
            vix_term_structure=-0.05,
            expected_move=8.50,
            expected_move_ratio=0.046,
            target_vega=0.32,
            target_vomma=0.0012,
            dim_iv_vol=72.0,
            dim_hv_vol=55.0,
        )
        text = render_volatility_context(ctx)

        assert "IV RANK: 85.0" in text
        assert "IV PERCENTILE: 90.0" in text
        assert "ATM IV 30D: 35.0" in text
        assert "BB WIDTH: 42.0" in text
        assert "ATR %: 15.3" in text
        assert "VOL REGIME: ELEVATED" in text
        assert "IV-HV SPREAD: 5.20" in text
        assert "SKEW RATIO: 1.15" in text
        assert "VIX TERM STRUCTURE: -0.05" in text
        assert "EXPECTED MOVE ($): 8.50" in text
        assert "EXPECTED MOVE RATIO: 0.05" in text
        assert "VEGA: 0.3200" in text
        assert "VOMMA: 0.001200" in text
        assert "IV VOLATILITY: 72.0" in text
        assert "HV VOLATILITY: 55.0" in text

    def test_excludes_scan_conclusions(self) -> None:
        """Verify COMPOSITE SCORE, DIRECTION excluded."""
        ctx = _make_context(
            composite_score=85.0,
            direction_signal=SignalDirection.BEARISH,
            direction_confidence=0.9,
        )
        text = render_volatility_context(ctx)

        assert "COMPOSITE SCORE" not in text
        assert "DIRECTION:" not in text
        assert "DIRECTION CONFIDENCE" not in text

    def test_handles_all_none(self) -> None:
        """Verify graceful handling when all vol fields are None."""
        ctx = _make_context(
            iv_rank=None,
            iv_percentile=None,
            atm_iv_30d=None,
            bb_width=None,
            atr_pct=None,
            vol_regime=None,
            iv_hv_spread=None,
            skew_ratio=None,
            vix_term_structure=None,
            expected_move=None,
            expected_move_ratio=None,
            target_vega=None,
            target_vomma=None,
            dim_iv_vol=None,
            dim_hv_vol=None,
        )
        text = render_volatility_context(ctx)

        # Identity block still present
        assert "TICKER: AAPL" in text
        assert "Volatility Indicators" in text
        # No vol-specific data lines after header
        assert "IV RANK:" not in text
        assert "Signal Dimensions" not in text

    def test_vol_regime_labels(self) -> None:
        """Verify vol regime renders human-readable labels."""
        for code, label in [(0.0, "NORMAL"), (1.0, "ELEVATED"), (2.0, "CRISIS")]:
            ctx = _make_context(vol_regime=code)
            text = render_volatility_context(ctx)
            assert f"VOL REGIME: {label}" in text


# ---------------------------------------------------------------------------
# render_flow_context
# ---------------------------------------------------------------------------


class TestRenderFlowContext:
    """Tests for the Flow agent's domain-specific renderer."""

    def test_includes_flow_indicators(self) -> None:
        """Verify P/C ratio, GEX, unusual activity present."""
        ctx = _make_context(
            put_call_ratio=0.85,
            max_pain_distance=3.5,
            gex=150000.0,
            unusual_activity_score=72.0,
            net_call_premium=5000000.0,
            net_put_premium=3000000.0,
            options_put_call_ratio=0.75,
            relative_volume=1.3,
            dim_flow=68.0,
            dim_microstructure=55.0,
        )
        text = render_flow_context(ctx)

        assert "PUT/CALL RATIO: 0.85" in text
        assert "MAX PAIN DISTANCE %: 3.5" in text
        assert "GEX: 150,000" in text
        assert "UNUSUAL ACTIVITY SCORE: 72.0" in text
        assert "NET CALL PREMIUM ($): 5,000,000" in text
        assert "NET PUT PREMIUM ($): 3,000,000" in text
        assert "OPTIONS PUT/CALL RATIO: 0.75" in text
        assert "REL VOLUME: 1.3" in text
        assert "FLOW: 68.0" in text
        assert "MICROSTRUCTURE: 55.0" in text

    def test_excludes_scan_conclusions(self) -> None:
        """Verify COMPOSITE SCORE, DIRECTION excluded."""
        ctx = _make_context(
            composite_score=85.0,
            direction_signal=SignalDirection.BULLISH,
            direction_confidence=0.8,
        )
        text = render_flow_context(ctx)

        assert "COMPOSITE SCORE" not in text
        assert "DIRECTION:" not in text
        assert "DIRECTION CONFIDENCE" not in text

    def test_handles_none_fields(self) -> None:
        """Verify None flow fields are omitted gracefully."""
        ctx = _make_context(
            put_call_ratio=None,
            max_pain_distance=None,
            gex=None,
            unusual_activity_score=None,
            net_call_premium=None,
            net_put_premium=None,
            options_put_call_ratio=None,
            relative_volume=None,
            dim_flow=None,
            dim_microstructure=None,
        )
        text = render_flow_context(ctx)

        assert "TICKER: AAPL" in text
        assert "PUT/CALL RATIO:" not in text
        assert "GEX:" not in text
        assert "Signal Dimensions" not in text


# ---------------------------------------------------------------------------
# render_fundamental_context
# ---------------------------------------------------------------------------


class TestRenderFundamentalContext:
    """Tests for the Fundamental agent's domain-specific renderer."""

    def test_includes_fundamental_indicators(self) -> None:
        """Verify PE, PEG, short interest, analyst data present."""
        ctx = _make_context(
            pe_ratio=28.5,
            forward_pe=25.0,
            peg_ratio=1.8,
            price_to_book=45.0,
            debt_to_equity=1.5,
            revenue_growth=0.12,
            profit_margin=0.25,
            short_ratio=2.5,
            short_pct_of_float=0.035,
            analyst_target_mean=200.0,
            analyst_target_upside_pct=0.078,
            analyst_consensus_score=0.65,
            analyst_upgrades_30d=3,
            analyst_downgrades_30d=1,
            insider_net_buys_90d=5,
            insider_buy_ratio=0.7,
            institutional_pct=0.72,
            news_sentiment=0.35,
            news_sentiment_label=SentimentLabel.BULLISH,
            recent_headlines=["Apple announces new product"],
            dim_fundamental=70.0,
        )
        text = render_fundamental_context(ctx)

        assert "P/E: 28.5" in text
        assert "FORWARD P/E: 25.0" in text
        assert "PEG: 1.80" in text
        assert "P/B: 45.00" in text
        assert "DEBT/EQUITY: 1.50" in text
        assert "REVENUE GROWTH: 12.0%" in text
        assert "PROFIT MARGIN: 25.0%" in text
        assert "SHORT RATIO: 2.50" in text
        assert "SHORT % OF FLOAT: 3.5%" in text
        assert "ANALYST TARGET MEAN: 200.00" in text
        assert "ANALYST TARGET UPSIDE: +7.8%" in text
        assert "ANALYST CONSENSUS: +0.65" in text
        assert "UPGRADES/DOWNGRADES (30D): 3/1" in text
        assert "INSIDER NET BUYS (90D): +5" in text
        assert "INSIDER BUY RATIO: 0.70" in text
        assert "INSTITUTIONAL OWNERSHIP: 72.0%" in text
        assert "Bullish (+0.35)" in text
        assert '"Apple announces new product"' in text
        assert "FUNDAMENTAL: 70.0" in text

    def test_excludes_scan_conclusions(self) -> None:
        """Verify COMPOSITE SCORE, DIRECTION excluded."""
        ctx = _make_context(
            composite_score=85.0,
            direction_signal=SignalDirection.BEARISH,
            direction_confidence=0.95,
        )
        text = render_fundamental_context(ctx)

        assert "COMPOSITE SCORE" not in text
        assert "DIRECTION:" not in text
        assert "DIRECTION CONFIDENCE" not in text

    def test_handles_all_none_fundamental_fields(self) -> None:
        """Verify all-None fundamental fields produce identity block only."""
        ctx = _make_context(
            pe_ratio=None,
            forward_pe=None,
            peg_ratio=None,
            price_to_book=None,
            debt_to_equity=None,
            revenue_growth=None,
            profit_margin=None,
            short_ratio=None,
            short_pct_of_float=None,
            analyst_target_mean=None,
            analyst_target_upside_pct=None,
            analyst_consensus_score=None,
            analyst_upgrades_30d=None,
            analyst_downgrades_30d=None,
            insider_net_buys_90d=None,
            insider_buy_ratio=None,
            institutional_pct=None,
            news_sentiment=None,
            dim_fundamental=None,
        )
        text = render_fundamental_context(ctx)

        assert "TICKER: AAPL" in text
        assert "Fundamental Profile" not in text
        assert "Analyst Intelligence" not in text
        assert "Insider Activity" not in text
        assert "Institutional Ownership" not in text
        assert "News Sentiment" not in text
        assert "Signal Dimension" not in text

    def test_news_sentiment_with_headlines(self) -> None:
        """Verify news sentiment section with headlines."""
        ctx = _make_context(
            news_sentiment=0.5,
            news_sentiment_label=SentimentLabel.BULLISH,
            recent_headlines=[
                "Strong earnings beat",
                "New product launch",
                "Analyst upgrade",
            ],
        )
        text = render_fundamental_context(ctx)

        assert "News Sentiment" in text
        assert "Bullish (+0.50)" in text
        assert '"Strong earnings beat"' in text
        assert '"New product launch"' in text
        assert '"Analyst upgrade"' in text

    def test_none_fundamental_fields_omitted(self) -> None:
        """Verify None fundamental fields are omitted.

        Note: MarketContext validators reject NaN/Inf values at construction
        time. This test verifies the None-handling path instead.
        """
        ctx = _make_context(
            pe_ratio=None,
            forward_pe=None,
            peg_ratio=None,
        )
        text = render_fundamental_context(ctx)

        assert "P/E:" not in text
        assert "FORWARD P/E:" not in text
        assert "PEG:" not in text


# ---------------------------------------------------------------------------
# PROMPT_RULES_APPENDIX
# ---------------------------------------------------------------------------


class TestPromptRulesAppendix:
    """Tests for PROMPT_RULES_APPENDIX after calibration update."""

    def test_no_composite_score_reference(self) -> None:
        """Verify COMPOSITE SCORE not in PROMPT_RULES_APPENDIX."""
        assert "COMPOSITE SCORE" not in PROMPT_RULES_APPENDIX

    def test_domain_neutral_calibration(self) -> None:
        """Verify domain-neutral calibration language present."""
        assert "domain-specific indicators" in PROMPT_RULES_APPENDIX
        assert "independent judgment" in PROMPT_RULES_APPENDIX
        assert "Indicators outside your domain" in PROMPT_RULES_APPENDIX

    def test_confidence_scale_preserved(self) -> None:
        """Verify the confidence calibration scale is still present."""
        assert "0.0-0.2" in PROMPT_RULES_APPENDIX
        assert "0.8-1.0" in PROMPT_RULES_APPENDIX

    def test_citation_rules_preserved(self) -> None:
        """Verify data citation rules are still present."""
        assert "Data citation rules" in PROMPT_RULES_APPENDIX
        assert "EXACT label" in PROMPT_RULES_APPENDIX

    def test_greeks_section_preserved(self) -> None:
        """Verify Greeks section is still present."""
        assert "DELTA: directional exposure" in PROMPT_RULES_APPENDIX
        assert "VEGA: IV sensitivity" in PROMPT_RULES_APPENDIX

    def test_version_updated(self) -> None:
        """Verify the version comment was updated from v2.0 to v3.0."""
        # The version is in a comment above the constant, not inside it.
        # We verify the constant content doesn't reference the old anchors.
        assert "direction matches: confidence MUST" not in PROMPT_RULES_APPENDIX
        assert "your confidence MUST NOT exceed" not in PROMPT_RULES_APPENDIX


# ---------------------------------------------------------------------------
# Cross-cutting: no scan conclusions in any domain renderer
# ---------------------------------------------------------------------------


class TestNoDomainRendererHasScanConclusions:
    """Verify that NO domain renderer includes COMPOSITE SCORE, DIRECTION,
    or DIRECTION CONFIDENCE in its output."""

    def test_all_renderers_exclude_scan_conclusions(self) -> None:
        """Parametric check across all 4 domain renderers."""
        ctx = _make_context(
            composite_score=99.0,
            direction_signal=SignalDirection.BULLISH,
            direction_confidence=0.99,
            # Populate all domain fields so renderers have data
            adx=30.0,
            iv_rank=80.0,
            put_call_ratio=0.9,
            pe_ratio=25.0,
            dim_trend=60.0,
            dim_iv_vol=70.0,
            dim_flow=55.0,
            dim_fundamental=65.0,
        )

        renderers = [
            render_trend_context,
            render_volatility_context,
            render_flow_context,
            render_fundamental_context,
        ]

        for renderer in renderers:
            text = renderer(ctx)
            assert "COMPOSITE SCORE" not in text, f"{renderer.__name__} contains COMPOSITE SCORE"
            # Check for "DIRECTION:" specifically to avoid matching "DIRECTION CONFIDENCE"
            # or "SignalDirection" in enum values or section header text.
            # Split into lines to check for standalone DIRECTION labels.
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("DIRECTION:"):
                    msg = f"{renderer.__name__} contains DIRECTION: line"
                    raise AssertionError(msg)
                if stripped.startswith("DIRECTION CONFIDENCE:"):
                    msg = f"{renderer.__name__} contains DIRECTION CONFIDENCE: line"
                    raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Financial Datasets (fd_*) context rendering
# ---------------------------------------------------------------------------


class TestFDContextRendering:
    """Tests for Financial Datasets context sections in renderers."""

    def test_income_statement_section_rendered(self) -> None:
        """Verify Income Statement section appears when fd_revenue set."""
        ctx = _make_context(fd_revenue=50_000_000_000.0)
        text = render_fundamental_context(ctx)

        assert "## Income Statement (TTM)" in text
        assert "REVENUE: $50.0B" in text

    def test_balance_sheet_section_rendered(self) -> None:
        """Verify Balance Sheet section appears when fd_total_debt set."""
        ctx = _make_context(fd_total_debt=25_000_000_000.0)
        text = render_fundamental_context(ctx)

        assert "## Balance Sheet" in text
        assert "TOTAL DEBT: $25.0B" in text

    def test_growth_valuation_section_rendered(self) -> None:
        """Verify Growth & Valuation section appears when fd_revenue_growth set."""
        ctx = _make_context(fd_revenue_growth=0.15)
        text = render_fundamental_context(ctx)

        assert "## Growth & Valuation" in text
        assert "REVENUE GROWTH (YOY): 15.0%" in text

    def test_sections_omitted_when_all_none(self) -> None:
        """Verify no FD sections when all fd_* fields are None."""
        ctx = _make_context()
        text = render_fundamental_context(ctx)

        assert "## Income Statement (TTM)" not in text
        assert "## Balance Sheet" not in text
        assert "## Growth & Valuation" not in text

    def test_partial_fields_render_only_populated(self) -> None:
        """Verify only non-None fields appear within a section."""
        ctx = _make_context(
            fd_revenue=100_000_000_000.0,
            fd_gross_margin=0.45,
            # fd_net_income, fd_operating_income, fd_eps_diluted, etc. are None
        )
        text = render_fundamental_context(ctx)

        assert "## Income Statement (TTM)" in text
        assert "REVENUE: $100.0B" in text
        assert "GROSS MARGIN: 45.0%" in text
        # Fields not set should not appear
        assert "NET INCOME:" not in text
        assert "OPERATING INCOME:" not in text
        assert "EPS (DILUTED):" not in text

    def test_dollar_formatting(self) -> None:
        """Verify revenue/income formatted as $X.XB or $X.XM."""
        # Test billions
        assert _format_dollars(50_000_000_000.0) == "$50.0B"
        assert _format_dollars(1_500_000_000.0) == "$1.5B"
        # Test millions
        assert _format_dollars(750_000_000.0) == "$750.0M"
        assert _format_dollars(5_000_000.0) == "$5.0M"
        # Test sub-million
        assert _format_dollars(500_000.0) == "$500,000"
        # Test negative
        assert _format_dollars(-2_000_000_000.0) == "$-2.0B"
        assert _format_dollars(-100_000_000.0) == "$-100.0M"

    def test_percentage_formatting(self) -> None:
        """Verify margin/growth fields formatted with %."""
        ctx = _make_context(
            fd_gross_margin=0.45,
            fd_operating_margin=0.30,
            fd_net_margin=0.25,
            fd_revenue_growth=0.12,
            fd_earnings_growth=-0.05,
            fd_free_cash_flow_yield=0.035,
        )
        text = render_fundamental_context(ctx)

        assert "GROSS MARGIN: 45.0%" in text
        assert "OPERATING MARGIN: 30.0%" in text
        assert "NET MARGIN: 25.0%" in text
        assert "REVENUE GROWTH (YOY): 12.0%" in text
        assert "EARNINGS GROWTH (YOY): -5.0%" in text
        assert "FCF YIELD: 3.5%" in text

    def test_context_block_includes_fd_sections(self) -> None:
        """Verify render_context_block() also renders FD sections."""
        ctx = _make_context(
            fd_revenue=50_000_000_000.0,
            fd_net_income=12_000_000_000.0,
            fd_total_debt=30_000_000_000.0,
            fd_current_ratio=1.5,
            fd_revenue_growth=0.08,
            fd_ev_to_ebitda=18.5,
        )
        text = render_context_block(ctx)

        # Income Statement
        assert "## Income Statement (TTM)" in text
        assert "REVENUE: $50.0B" in text
        assert "NET INCOME: $12.0B" in text
        # Balance Sheet
        assert "## Balance Sheet" in text
        assert "TOTAL DEBT: $30.0B" in text
        assert "CURRENT RATIO: 1.5x" in text
        # Growth & Valuation
        assert "## Growth & Valuation" in text
        assert "REVENUE GROWTH (YOY): 8.0%" in text
        assert "EV/EBITDA: 18.5x" in text

    def test_ev_to_ebitda_formatting(self) -> None:
        """Verify EV/EBITDA formatted as ratio with x suffix."""
        ctx = _make_context(fd_ev_to_ebitda=12.5)
        text = render_fundamental_context(ctx)

        assert "EV/EBITDA: 12.5x" in text

    def test_current_ratio_formatting(self) -> None:
        """Verify current ratio formatted with x suffix."""
        ctx = _make_context(fd_current_ratio=2.3)
        text = render_fundamental_context(ctx)

        assert "CURRENT RATIO: 2.3x" in text

    def test_eps_formatting(self) -> None:
        """Verify EPS formatted with dollar sign and 2 decimals."""
        ctx = _make_context(fd_eps_diluted=6.42)
        text = render_fundamental_context(ctx)

        assert "EPS (DILUTED): $6.42" in text
