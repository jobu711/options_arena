"""Tests for spread recommendation rendering.

Tests verify table structure, column names, row contents, and formatting --
NOT Rich-rendered terminal output, which is terminal-dependent and fragile.
"""

from __future__ import annotations

from decimal import Decimal

from rich.table import Table
from rich.text import Text

from options_arena.cli.rendering import render_spread_recommendation
from options_arena.models.options import SpreadAnalysis
from tests.factories import make_spread_analysis


class TestSpreadRendering:
    """Tests for ``render_spread_recommendation()``."""

    def test_renders_rich_table(self) -> None:
        """Returns a Rich Table object."""
        spread = make_spread_analysis()
        result = render_spread_recommendation(spread)
        assert isinstance(result, Table)

    def test_contains_strategy_type(self) -> None:
        """Table includes spread strategy type row."""
        spread = make_spread_analysis()
        table = render_spread_recommendation(spread)
        # First column contains metric names
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        assert "Strategy Type" in metrics

    def test_contains_pnl_metrics(self) -> None:
        """Table includes net premium, max profit, max loss."""
        spread = make_spread_analysis()
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        assert "Net Premium" in metrics
        assert "Max Profit" in metrics
        assert "Max Loss" in metrics

    def test_decimal_formatting(self) -> None:
        """Decimal values formatted to 2 decimal places with $ prefix."""
        spread = make_spread_analysis(
            net_premium=Decimal("3.75"),
            max_profit=Decimal("1.25"),
            max_loss=Decimal("3.75"),
        )
        table = render_spread_recommendation(spread)
        value_col = table.columns[1]
        values = list(value_col._cells)  # type: ignore[attr-defined]

        # Net Premium is the second row (index 1), formatted as "$3.75"
        # Find the value corresponding to "Net Premium"
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        net_premium_idx = metrics.index("Net Premium")
        assert values[net_premium_idx] == "$3.75"

        # Max Profit is a Text object with style
        max_profit_idx = metrics.index("Max Profit")
        max_profit_val = values[max_profit_idx]
        assert isinstance(max_profit_val, Text)
        assert str(max_profit_val) == "$1.25"

        # Max Loss is a Text object with style
        max_loss_idx = metrics.index("Max Loss")
        max_loss_val = values[max_loss_idx]
        assert isinstance(max_loss_val, Text)
        assert str(max_loss_val) == "$3.75"

    def test_percentage_formatting(self) -> None:
        """P(profit) formatted as percentage with 1 decimal."""
        spread = make_spread_analysis(pop_estimate=0.653)
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        value_col = table.columns[1]
        values = list(value_col._cells)  # type: ignore[attr-defined]

        pop_idx = metrics.index("P(Profit)")
        assert values[pop_idx] == "65.3%"

    def test_risk_reward_none_displays_dash(self) -> None:
        """risk_reward_ratio=None displays '--'."""
        spread = make_spread_analysis(risk_reward_ratio=None)
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        value_col = table.columns[1]
        values = list(value_col._cells)  # type: ignore[attr-defined]

        rr_idx = metrics.index("Risk/Reward")
        assert values[rr_idx] == "--"

    def test_risk_reward_present_displays_yellow(self) -> None:
        """risk_reward_ratio with a value displays in yellow."""
        spread = make_spread_analysis(risk_reward_ratio=2.5)
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        value_col = table.columns[1]
        values = list(value_col._cells)  # type: ignore[attr-defined]

        rr_idx = metrics.index("Risk/Reward")
        rr_val = values[rr_idx]
        assert isinstance(rr_val, Text)
        assert str(rr_val) == "2.50"

    def test_table_has_two_columns(self) -> None:
        """Spread table has exactly 2 columns: Metric, Value."""
        spread = make_spread_analysis()
        table = render_spread_recommendation(spread)
        assert len(table.columns) == 2
        column_names = [col.header for col in table.columns]  # type: ignore[union-attr]
        assert column_names == ["Metric", "Value"]

    def test_rationale_included_when_present(self) -> None:
        """Rationale row is present when strategy_rationale is non-empty."""
        spread = make_spread_analysis(strategy_rationale="Bull call spread for upside exposure")
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        assert "Rationale" in metrics

    def test_rationale_omitted_when_empty(self) -> None:
        """Rationale row is omitted when strategy_rationale is empty."""
        spread = make_spread_analysis(strategy_rationale="")
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        assert "Rationale" not in metrics

    def test_zero_max_loss_displays_zero(self) -> None:
        """Zero max_loss displays as '$0.00'."""
        spread = make_spread_analysis(max_loss=Decimal("0.00"))
        table = render_spread_recommendation(spread)
        metric_col = table.columns[0]
        metrics = list(metric_col._cells)  # type: ignore[attr-defined]
        value_col = table.columns[1]
        values = list(value_col._cells)  # type: ignore[attr-defined]

        max_loss_idx = metrics.index("Max Loss")
        max_loss_val = values[max_loss_idx]
        assert isinstance(max_loss_val, Text)
        assert str(max_loss_val) == "$0.00"

    def test_type_annotation_accepted(self) -> None:
        """Function accepts SpreadAnalysis type (not dict or other)."""
        spread = make_spread_analysis()
        assert isinstance(spread, SpreadAnalysis)
        # Should not raise
        render_spread_recommendation(spread)
