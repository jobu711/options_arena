"""Tests for neural context rendering and live _parsing.py functions.

Verifies that ``_render_neural_context()`` produces correct output when neural
fields are populated, and produces empty strings when neural features are
disabled (``None`` fields).

Also verifies ``PROMPT_RULES_APPENDIX`` content, ``render_context_block()``
integration with Financial Datasets sections, and ``_format_dollars()`` formatting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX,
    _format_dollars,
    _render_neural_context,
    render_context_block,
)
from options_arena.models import (
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    SignalDirection,
)


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
# _render_neural_context
# ---------------------------------------------------------------------------


class TestRenderNeuralContext:
    """Tests for neural trajectory probability rendering."""

    def test_renders_prob_profit_when_available(self) -> None:
        """Verify prob_profit_neural appears in rendered context."""
        ctx = _make_context(prob_profit_neural=0.65)
        result = _render_neural_context(ctx)

        assert "Neural Trajectory" in result
        assert "NEURAL P(PROFIT)" in result

    def test_empty_when_none(self) -> None:
        """Verify empty string when prob_profit_neural is None."""
        ctx = _make_context(prob_profit_neural=None)
        result = _render_neural_context(ctx)

        assert result == ""

    def test_isfinite_guard(self) -> None:
        """Verify NaN/Inf prob_profit_neural is rejected by model validator.

        MarketContext has a ``validate_optional_finite`` + ``validate_prob_profit_neural``
        validator that rejects non-finite values at the boundary. The rendering layer's
        ``_render_optional()`` provides defense-in-depth, but the model guard fires first.
        """
        import pydantic

        for bad_value in [float("nan"), float("inf"), float("-inf")]:
            with pytest.raises(pydantic.ValidationError, match="prob_profit_neural"):
                _make_context(prob_profit_neural=bad_value)

    def test_percentage_format(self) -> None:
        """Verify probability rendered as percentage (e.g., '65.0%')."""
        ctx = _make_context(prob_profit_neural=0.65)
        result = _render_neural_context(ctx)

        assert "65.0%" in result

    def test_zero_probability(self) -> None:
        """Verify 0.0 probability renders correctly."""
        ctx = _make_context(prob_profit_neural=0.0)
        result = _render_neural_context(ctx)

        assert "NEURAL P(PROFIT): 0.0%" in result

    def test_full_probability(self) -> None:
        """Verify 1.0 probability renders correctly."""
        ctx = _make_context(prob_profit_neural=1.0)
        result = _render_neural_context(ctx)

        assert "NEURAL P(PROFIT): 100.0%" in result

    def test_context_block_includes_neural(self) -> None:
        """Verify render_context_block() includes neural section."""
        ctx = _make_context(prob_profit_neural=0.72)
        block = render_context_block(ctx)

        assert "Neural Trajectory" in block
        assert "NEURAL P(PROFIT)" in block
        assert "72.0%" in block

    def test_context_block_omits_when_none(self) -> None:
        """Verify render_context_block() excludes neural section when None."""
        ctx = _make_context(prob_profit_neural=None)
        block = render_context_block(ctx)

        assert "Neural Trajectory" not in block
        assert "NEURAL P(PROFIT)" not in block


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
# Financial Datasets (fd_*) context rendering
# ---------------------------------------------------------------------------


class TestFDContextRendering:
    """Tests for Financial Datasets context sections in renderers."""

    def test_income_statement_section_rendered(self) -> None:
        """Verify Income Statement section appears when fd_revenue set."""
        ctx = _make_context(fd_revenue=50_000_000_000.0)
        text = render_context_block(ctx)

        assert "## Income Statement (TTM)" in text
        assert "REVENUE: $50.0B" in text

    def test_balance_sheet_section_rendered(self) -> None:
        """Verify Balance Sheet section appears when fd_total_debt set."""
        ctx = _make_context(fd_total_debt=25_000_000_000.0)
        text = render_context_block(ctx)

        assert "## Balance Sheet" in text
        assert "TOTAL DEBT: $25.0B" in text

    def test_growth_valuation_section_rendered(self) -> None:
        """Verify Growth & Valuation section appears when fd_revenue_growth set."""
        ctx = _make_context(fd_revenue_growth=0.15)
        text = render_context_block(ctx)

        assert "## Growth & Valuation" in text
        assert "REVENUE GROWTH (YOY): 15.0%" in text

    def test_sections_omitted_when_all_none(self) -> None:
        """Verify no FD sections when all fd_* fields are None."""
        ctx = _make_context()
        text = render_context_block(ctx)

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
        text = render_context_block(ctx)

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
        text = render_context_block(ctx)

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
        text = render_context_block(ctx)

        assert "EV/EBITDA: 12.5x" in text

    def test_current_ratio_formatting(self) -> None:
        """Verify current ratio formatted with x suffix."""
        ctx = _make_context(fd_current_ratio=2.3)
        text = render_context_block(ctx)

        assert "CURRENT RATIO: 2.3x" in text

    def test_eps_formatting(self) -> None:
        """Verify EPS formatted with dollar sign and 2 decimals."""
        ctx = _make_context(fd_eps_diluted=6.42)
        text = render_context_block(ctx)

        assert "EPS (DILUTED): $6.42" in text
