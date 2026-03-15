"""Tests for CLI spread rendering (#521).

Tests verify render_spread_panel behavior with Rich Console capture.
Follows the project pattern: test data shapes and key content, NOT
terminal-specific rendering (which is fragile).
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from rich.console import Console

from options_arena.cli.rendering import render_spread_panel
from options_arena.models import SpreadAnalysis
from tests.factories import make_option_contract, make_spread_analysis, make_spread_leg


def _capture_spread_output(spread: SpreadAnalysis) -> str:
    """Render a spread and capture the console output as plain text."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)
    render_spread_panel(console, spread)
    return buf.getvalue()


class TestRenderSpreadPanel:
    """Tests for render_spread_panel function."""

    def test_spread_table_renders(self) -> None:
        """Spread panel renders with strategy type and legs table."""
        spread = make_spread_analysis()
        output = _capture_spread_output(spread)

        # Strategy type displayed
        assert "VERTICAL" in output
        # Table title
        assert "Spread Legs" in output
        # Column headers present
        assert "Side" in output
        assert "Strike" in output
        assert "Exp" in output

    def test_two_legs_displayed(self) -> None:
        """Both legs of a vertical spread are rendered."""
        spread = make_spread_analysis()
        output = _capture_spread_output(spread)

        # Both leg sides should appear
        assert "LONG" in output
        assert "SHORT" in output

    def test_pnl_summary_displayed(self) -> None:
        """P&L summary shows net premium, max profit, max loss."""
        spread = make_spread_analysis(
            net_premium=Decimal("3.00"),
            max_profit=Decimal("2.00"),
            max_loss=Decimal("3.00"),
        )
        output = _capture_spread_output(spread)

        assert "Net Premium: $3.00" in output
        assert "Max Profit: $2.00" in output
        assert "Max Loss: $3.00" in output

    def test_pop_and_risk_reward_displayed(self) -> None:
        """PoP and risk/reward ratio are shown."""
        spread = make_spread_analysis(
            pop_estimate=0.65,
            risk_reward_ratio=2.50,
        )
        output = _capture_spread_output(spread)

        assert "PoP: 65.0%" in output
        assert "Risk/Reward: 2.50" in output

    def test_nan_risk_reward_shows_dash(self) -> None:
        """NaN risk_reward_ratio displays as '--'."""
        spread = make_spread_analysis(risk_reward_ratio=float("nan"))
        output = _capture_spread_output(spread)

        assert "Risk/Reward: --" in output

    def test_unlimited_max_profit(self) -> None:
        """Sentinel Decimal('999999.99') displays as 'Unlimited'."""
        spread = make_spread_analysis(max_profit=Decimal("999999.99"))
        output = _capture_spread_output(spread)

        assert "Unlimited" in output

    def test_four_leg_iron_condor(self) -> None:
        """Iron condor with 4 legs renders all legs."""
        from options_arena.models.enums import PositionSide, SpreadType
        from options_arena.models.options import OptionSpread

        legs = [
            make_spread_leg(
                contract=make_option_contract(
                    strike=Decimal("140.00"),
                    option_type="put",
                ),
                side=PositionSide.LONG,
            ),
            make_spread_leg(
                contract=make_option_contract(
                    strike=Decimal("145.00"),
                    option_type="put",
                ),
                side=PositionSide.SHORT,
            ),
            make_spread_leg(
                contract=make_option_contract(
                    strike=Decimal("155.00"),
                    option_type="call",
                ),
                side=PositionSide.SHORT,
            ),
            make_spread_leg(
                contract=make_option_contract(
                    strike=Decimal("160.00"),
                    option_type="call",
                ),
                side=PositionSide.LONG,
            ),
        ]
        ic_spread = OptionSpread(
            spread_type=SpreadType.IRON_CONDOR,
            legs=legs,
            ticker="AAPL",
        )
        analysis = make_spread_analysis(spread=ic_spread)
        output = _capture_spread_output(analysis)

        assert "IRON_CONDOR" in output
        # All 4 strikes should appear in output
        assert "$140.00" in output
        assert "$145.00" in output
        assert "$155.00" in output
        assert "$160.00" in output

    def test_missing_delta_shows_dash(self) -> None:
        """Contract without greeks shows '--' for delta."""
        # Default factory creates contracts with greeks=None
        spread = make_spread_analysis()
        output = _capture_spread_output(spread)

        # greeks is None on factory-built contracts, so delta shows --
        assert "--" in output
