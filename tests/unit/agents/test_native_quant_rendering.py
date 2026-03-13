"""Tests for native quant rendering in debate agent context blocks.

Verifies that vol surface analytics (HV Yang-Zhang, 25-delta skew, smile
curvature, risk-neutral probability) and second-order Greeks (vanna, charm,
vomma) render correctly in both the general context block and domain-specific
renderers. Also verifies prompt guidance keywords in volatility and risk
agent prompts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from options_arena.agents._parsing import (
    render_context_block,
    render_volatility_context,
)
from options_arena.agents.prompts.risk import RISK_SYSTEM_PROMPT
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT
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
# Vol surface rendering in render_context_block
# ---------------------------------------------------------------------------


class TestVolSurfaceContextBlock:
    """Tests for vol surface fields in the general context block."""

    def test_all_four_fields_rendered(self) -> None:
        """Verify all 4 vol surface fields render when all are populated."""
        ctx = _make_context(
            hv_yang_zhang=0.285,
            skew_25d=-0.042,
            smile_curvature=0.015,
            prob_above_current=0.52,
        )
        text = render_context_block(ctx)

        assert "## HV & Vol Surface" in text
        assert "HV YANG-ZHANG: 28.5%" in text
        assert "SKEW 25D: -0.042" in text
        assert "SMILE CURVATURE: 0.015" in text
        assert "PROB ABOVE CURRENT: 52.0%" in text

    def test_partial_fields_rendered(self) -> None:
        """Verify only non-None fields appear when some are None."""
        ctx = _make_context(
            hv_yang_zhang=0.32,
            skew_25d=None,
            smile_curvature=None,
            prob_above_current=0.48,
        )
        text = render_context_block(ctx)

        assert "## HV & Vol Surface" in text
        assert "HV YANG-ZHANG: 32.0%" in text
        assert "SKEW 25D:" not in text
        assert "SMILE CURVATURE:" not in text
        assert "PROB ABOVE CURRENT: 48.0%" in text

    def test_no_section_header_when_all_none(self) -> None:
        """Verify no empty HV & Vol Surface header when all fields are None."""
        ctx = _make_context(
            hv_yang_zhang=None,
            skew_25d=None,
            smile_curvature=None,
            prob_above_current=None,
        )
        text = render_context_block(ctx)

        assert "## HV & Vol Surface" not in text

    def test_skew_decimal_format(self) -> None:
        """Verify skew_25d renders with 3 decimal places."""
        ctx = _make_context(skew_25d=-0.0567)
        text = render_context_block(ctx)

        assert "SKEW 25D: -0.057" in text

    def test_curvature_decimal_format(self) -> None:
        """Verify smile_curvature renders with 3 decimal places."""
        ctx = _make_context(smile_curvature=0.0234)
        text = render_context_block(ctx)

        assert "SMILE CURVATURE: 0.023" in text

    def test_prob_percentage_format(self) -> None:
        """Verify prob_above_current renders as percentage with 1 decimal."""
        ctx = _make_context(prob_above_current=0.623)
        text = render_context_block(ctx)

        assert "PROB ABOVE CURRENT: 62.3%" in text

    def test_hv_percentage_format(self) -> None:
        """Verify hv_yang_zhang renders as percentage with 1 decimal."""
        ctx = _make_context(hv_yang_zhang=0.4215)
        text = render_context_block(ctx)

        assert "HV YANG-ZHANG: 42.1%" in text


# ---------------------------------------------------------------------------
# Vol surface rendering in render_volatility_context
# ---------------------------------------------------------------------------


class TestVolSurfaceVolatilityContext:
    """Tests for vol surface fields in the volatility domain renderer."""

    def test_vol_surface_section_in_volatility_context(self) -> None:
        """Verify HV & Vol Surface section appears in volatility context."""
        ctx = _make_context(
            hv_yang_zhang=0.30,
            skew_25d=-0.035,
            smile_curvature=0.012,
            prob_above_current=0.55,
        )
        text = render_volatility_context(ctx)

        assert "## HV & Vol Surface" in text
        assert "HV YANG-ZHANG: 30.0%" in text
        assert "SKEW 25D: -0.035" in text
        assert "SMILE CURVATURE: 0.012" in text
        assert "PROB ABOVE CURRENT: 55.0%" in text

    def test_no_vol_surface_section_when_all_none(self) -> None:
        """Verify no HV & Vol Surface section when all fields are None."""
        ctx = _make_context(
            hv_yang_zhang=None,
            skew_25d=None,
            smile_curvature=None,
            prob_above_current=None,
        )
        text = render_volatility_context(ctx)

        assert "## HV & Vol Surface" not in text


# ---------------------------------------------------------------------------
# Second-order Greeks rendering
# ---------------------------------------------------------------------------


class TestSecondOrderGreeksRendering:
    """Tests for second-order Greeks in the general context block."""

    def test_all_second_order_greeks_rendered(self) -> None:
        """Verify vanna, charm, vomma render when all populated."""
        ctx = _make_context(
            target_vanna=0.001234,
            target_charm=-0.003420,
            target_vomma=0.000567,
        )
        text = render_context_block(ctx)

        assert "## Second-Order Greeks" in text
        assert "VANNA: 0.001234" in text
        assert "CHARM: -0.003420" in text
        assert "VOMMA: 0.000567" in text

    def test_partial_second_order_greeks(self) -> None:
        """Verify partial second-order Greeks render, others omitted."""
        ctx = _make_context(
            target_vanna=0.002500,
            target_charm=None,
            target_vomma=None,
        )
        text = render_context_block(ctx)

        assert "## Second-Order Greeks" in text
        assert "VANNA: 0.002500" in text
        assert "CHARM:" not in text
        assert "VOMMA:" not in text

    def test_no_section_when_all_none(self) -> None:
        """Verify no Second-Order Greeks section when all are None."""
        ctx = _make_context(
            target_vanna=None,
            target_charm=None,
            target_vomma=None,
        )
        text = render_context_block(ctx)

        assert "## Second-Order Greeks" not in text


# ---------------------------------------------------------------------------
# Volatility prompt guidance keywords
# ---------------------------------------------------------------------------


class TestVolatilityPromptGuidance:
    """Tests for vol surface interpretation guidance in the volatility prompt."""

    def test_contains_skew_25d_guidance(self) -> None:
        """Verify SKEW 25D interpretation guidance is in volatility prompt."""
        assert "SKEW 25D" in VOLATILITY_SYSTEM_PROMPT
        assert "25-delta puts and calls" in VOLATILITY_SYSTEM_PROMPT

    def test_contains_smile_curvature_guidance(self) -> None:
        """Verify SMILE CURVATURE interpretation guidance is in volatility prompt."""
        assert "SMILE CURVATURE" in VOLATILITY_SYSTEM_PROMPT
        assert "Convexity" in VOLATILITY_SYSTEM_PROMPT

    def test_contains_prob_above_current_guidance(self) -> None:
        """Verify PROB ABOVE CURRENT interpretation guidance is in volatility prompt."""
        assert "PROB ABOVE CURRENT" in VOLATILITY_SYSTEM_PROMPT
        assert "risk-neutral probability" in VOLATILITY_SYSTEM_PROMPT.lower()

    def test_contains_hv_yang_zhang_guidance(self) -> None:
        """Verify HV YANG-ZHANG interpretation guidance is in volatility prompt."""
        assert "HV YANG-ZHANG" in VOLATILITY_SYSTEM_PROMPT
        assert "Yang-Zhang" in VOLATILITY_SYSTEM_PROMPT
        assert "OHLC" in VOLATILITY_SYSTEM_PROMPT

    def test_vol_surface_section_header(self) -> None:
        """Verify the Vol Surface Analytics Interpretation section header exists."""
        assert "Vol Surface Analytics Interpretation" in VOLATILITY_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Risk prompt guidance keywords
# ---------------------------------------------------------------------------


class TestRiskPromptGuidance:
    """Tests for second-order Greeks guidance in the risk prompt."""

    def test_contains_vanna_guidance(self) -> None:
        """Verify VANNA interpretation guidance is in risk prompt."""
        assert "VANNA" in RISK_SYSTEM_PROMPT
        assert "dDelta/dSigma" in RISK_SYSTEM_PROMPT

    def test_contains_charm_guidance(self) -> None:
        """Verify CHARM interpretation guidance is in risk prompt."""
        assert "CHARM" in RISK_SYSTEM_PROMPT
        assert "dDelta/dTime" in RISK_SYSTEM_PROMPT

    def test_contains_vomma_guidance(self) -> None:
        """Verify VOMMA interpretation guidance is in risk prompt."""
        assert "VOMMA" in RISK_SYSTEM_PROMPT
        assert "dVega/dSigma" in RISK_SYSTEM_PROMPT

    def test_second_order_greeks_section_header(self) -> None:
        """Verify the Second-Order Greeks Analysis section header exists."""
        assert "Second-Order Greeks Analysis" in RISK_SYSTEM_PROMPT
