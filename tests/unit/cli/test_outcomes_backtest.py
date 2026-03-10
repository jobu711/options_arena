"""Tests for outcomes backtest and equity-curve CLI subcommands.

Covers: backtest (with data, empty, filtered), equity-curve (with data, empty,
direction filter, period filter).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli import app
from options_arena.models import DrawdownPoint, EquityCurvePoint, HoldingPeriodComparison

runner = CliRunner()


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


def _sample_comparisons() -> list[HoldingPeriodComparison]:
    """Build sample HoldingPeriodComparison data for tests."""
    return [
        HoldingPeriodComparison(
            holding_days=5,
            direction="bullish",
            avg_return=3.5,
            median_return=2.1,
            win_rate=0.65,
            sharpe_like=1.2,
            max_loss=-8.5,
            count=30,
        ),
        HoldingPeriodComparison(
            holding_days=20,
            direction="bullish",
            avg_return=5.2,
            median_return=3.8,
            win_rate=0.70,
            sharpe_like=1.5,
            max_loss=-12.3,
            count=25,
        ),
        HoldingPeriodComparison(
            holding_days=20,
            direction="bearish",
            avg_return=-1.3,
            median_return=-2.0,
            win_rate=0.40,
            sharpe_like=-0.3,
            max_loss=-25.0,
            count=15,
        ),
    ]


def _sample_equity_curve() -> list[EquityCurvePoint]:
    """Build sample equity curve for tests."""
    return [
        EquityCurvePoint(date=date(2026, 1, 10), cumulative_return_pct=1.5, trade_count=3),
        EquityCurvePoint(date=date(2026, 1, 20), cumulative_return_pct=4.2, trade_count=8),
        EquityCurvePoint(date=date(2026, 2, 1), cumulative_return_pct=6.8, trade_count=15),
    ]


def _sample_drawdown_series() -> list[DrawdownPoint]:
    """Build sample drawdown series for tests."""
    return [
        DrawdownPoint(date=date(2026, 1, 10), drawdown_pct=0.0, peak_value=101.5),
        DrawdownPoint(date=date(2026, 1, 15), drawdown_pct=-2.1, peak_value=101.5),
        DrawdownPoint(date=date(2026, 1, 20), drawdown_pct=0.0, peak_value=104.2),
    ]


class TestBacktestCLI:
    """Tests for outcomes backtest command."""

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_basic_output(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify Rich table renders with mock data for default holding period."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_holding_period_comparison = AsyncMock(return_value=_sample_comparisons())
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo.get_drawdown_series = AsyncMock(return_value=_sample_drawdown_series())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "backtest"])
        assert result.exit_code == 0
        assert "T+20" in result.output
        assert "BULLISH" in result.output
        assert "BEARISH" in result.output
        assert "70.0" in result.output  # win rate for bullish T+20

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_holding_days_option(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify --holding-days filters to the specified period."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_holding_period_comparison = AsyncMock(return_value=_sample_comparisons())
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo.get_drawdown_series = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "backtest", "--holding-days", "5"])
        assert result.exit_code == 0
        assert "T+5" in result.output
        assert "BULLISH" in result.output
        # Should NOT contain T+20 data
        assert "BEARISH" not in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_data_message(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify informative message when no outcome data exists."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_holding_period_comparison = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "backtest"])
        assert result.exit_code == 0
        assert "No outcome data found" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_matching_period(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify message when no data for specified holding period."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        # Only has T+5, asking for T+10
        mock_repo.get_holding_period_comparison = AsyncMock(
            return_value=[
                HoldingPeriodComparison(
                    holding_days=5,
                    direction="bullish",
                    avg_return=3.5,
                    median_return=2.1,
                    win_rate=0.65,
                    sharpe_like=1.2,
                    max_loss=-8.5,
                    count=30,
                ),
            ]
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "backtest", "--holding-days", "10"])
        assert result.exit_code == 0
        assert "No data for 10-day" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_equity_curve_summary_shown(
        self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock
    ) -> None:
        """Verify equity curve summary line appears below table."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_holding_period_comparison = AsyncMock(return_value=_sample_comparisons())
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo.get_drawdown_series = AsyncMock(return_value=_sample_drawdown_series())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "backtest"])
        assert result.exit_code == 0
        assert "cumulative" in result.output.lower()
        assert "15 trades" in result.output
        assert "drawdown" in result.output.lower()


class TestEquityCurveCLI:
    """Tests for outcomes equity-curve command."""

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_basic_output(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify equity curve table renders with mock data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "equity-curve"])
        assert result.exit_code == 0
        assert "Equity Curve" in result.output
        assert "2026-01-10" in result.output
        assert "+6.80" in result.output  # last point cumulative return
        assert "15" in result.output  # trade count

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_data_message(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify informative message when no equity curve data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "equity-curve"])
        assert result.exit_code == 0
        assert "No equity curve data found" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_direction_filter(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify --direction is passed through and shown in title."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "equity-curve", "--direction", "bullish"])
        assert result.exit_code == 0
        assert "BULLISH" in result.output
        mock_repo.get_equity_curve.assert_called_once_with(direction="bullish", period_days=None)

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_period_filter(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify --period is passed through and shown in title."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_equity_curve = AsyncMock(return_value=_sample_equity_curve())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "equity-curve", "--period", "30"])
        assert result.exit_code == 0
        assert "last 30 days" in result.output
        mock_repo.get_equity_curve.assert_called_once_with(direction=None, period_days=30)

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_data_with_filters_message(
        self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock
    ) -> None:
        """Verify message includes filter hint when filters active and no data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_equity_curve = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "equity-curve", "--direction", "bearish"])
        assert result.exit_code == 0
        assert "adjusting filters" in result.output.lower()
