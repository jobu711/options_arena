"""Tests for spread section in debate export (#521).

Tests cover:
  - Markdown includes spread section when spread is provided
  - Markdown omits spread section when spread is None
  - Spread P&L details appear in markdown output
  - NaN risk/reward displays as N/A
  - Unlimited max profit sentinel displays as Unlimited
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from options_arena.reporting.debate_export import (
    export_debate_markdown,
    export_debate_to_file,
)
from tests.factories import make_debate_result, make_spread_analysis


class TestMarkdownSpreadSection:
    """Tests for spread section in markdown export."""

    def test_markdown_includes_spread_section(self) -> None:
        """Markdown export contains spread strategy section when provided."""
        spread = make_spread_analysis(strategy_rationale="Risk-managed directional play.")
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        assert "## Spread Strategy: VERTICAL" in md
        assert "| Leg | Side | Type | Strike | Expiration | Delta |" in md

    def test_markdown_omits_spread_when_none(self) -> None:
        """No spread section when spread is None."""
        result = make_debate_result()
        md = export_debate_markdown(result, spread=None)

        assert "## Spread Strategy" not in md

    def test_markdown_spread_pnl_details(self) -> None:
        """Spread P&L table shows net premium, max profit, max loss."""
        spread = make_spread_analysis(
            net_premium=Decimal("3.00"),
            max_profit=Decimal("2.00"),
            max_loss=Decimal("3.00"),
        )
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        assert "| Net Premium | $3.00 |" in md
        assert "| Max Profit | $2.00 |" in md
        assert "| Max Loss | $3.00 |" in md

    def test_markdown_spread_risk_metrics(self) -> None:
        """Spread risk metrics (PoP, Risk/Reward) appear in P&L table."""
        spread = make_spread_analysis(
            pop_estimate=0.65,
            risk_reward_ratio=2.50,
        )
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        assert "| PoP | 65.0% |" in md
        assert "| Risk/Reward | 2.50 |" in md

    def test_markdown_nan_risk_reward_shows_na(self) -> None:
        """NaN risk_reward_ratio displays as 'N/A' in P&L table."""
        spread = make_spread_analysis(risk_reward_ratio=float("nan"))
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        assert "| Risk/Reward | N/A |" in md

    def test_markdown_unlimited_max_profit(self) -> None:
        """Sentinel Decimal('999999.99') displays as 'Unlimited' in markdown."""
        spread = make_spread_analysis(max_profit=Decimal("999999.99"))
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        assert "Unlimited" in md

    def test_markdown_spread_leg_count(self) -> None:
        """Two-leg vertical spread shows 2 data rows in the table."""
        spread = make_spread_analysis()
        result = make_debate_result()
        md = export_debate_markdown(result, spread=spread)

        # Count table data rows (lines starting with "| 1" and "| 2")
        lines = md.split("\n")
        leg_rows = [line for line in lines if line.startswith("| 1 ") or line.startswith("| 2 ")]
        assert len(leg_rows) == 2

    def test_file_export_passes_spread(self, tmp_path: Path) -> None:
        """export_debate_to_file passes spread through to markdown."""
        spread = make_spread_analysis()
        result = make_debate_result()
        dest = tmp_path / "report.md"

        export_debate_to_file(result, dest, fmt="md", spread=spread)

        content = dest.read_text(encoding="utf-8")
        assert "## Spread Strategy: VERTICAL" in content
