"""Tests for correlation matrix and risk-adjusted metrics tool wrappers."""

from __future__ import annotations

import inspect
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_correlation_matrix_tool,
    compute_risk_adjusted_metrics_tool,
)
from options_arena.models.analytics import RiskAdjustedMetrics

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_ctx(deps: DeskDeps) -> MagicMock:
    """Create a mock RunContext with the given deps."""
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


def _make_deps(**overrides: object) -> DeskDeps:
    """Create a DeskDeps with mocked services and optional overrides."""
    defaults: dict[str, object] = {
        "query": "test query",
        "ticker": "AAPL",
        "market_data": AsyncMock(),
        "options_data": AsyncMock(),
        "fred": AsyncMock(),
        "repo": AsyncMock(),
    }
    defaults.update(overrides)
    return DeskDeps(**defaults)  # type: ignore[arg-type]


def _make_mock_ohlcv_bar(
    date_val: str = "2026-01-15",
    open_: float = 185.0,
    high: float = 187.0,
    low: float = 184.0,
    close: float = 186.0,
    volume: int = 1_000_000,
) -> MagicMock:
    """Create a mock OHLCV bar."""
    from datetime import date

    bar = MagicMock()
    bar.date = date.fromisoformat(date_val)
    bar.open = Decimal(str(open_))
    bar.high = Decimal(str(high))
    bar.low = Decimal(str(low))
    bar.close = Decimal(str(close))
    bar.volume = volume
    return bar


def _make_ohlcv_series(n: int = 50, base_price: float = 100.0) -> list[MagicMock]:
    """Create a list of mock OHLCV bars with increasing dates."""
    from datetime import date, timedelta

    bars: list[MagicMock] = []
    start_date = date(2025, 6, 1)
    for i in range(n):
        price = base_price + i * 0.5
        bars.append(
            _make_mock_ohlcv_bar(
                date_val=(start_date + timedelta(days=i)).isoformat(),
                open_=price - 0.5,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
            )
        )
    return bars


# ---------------------------------------------------------------------------
# Test: compute_correlation_matrix_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCorrelationMatrixTool:
    """Test the compute_correlation_matrix_tool wrapper."""

    @pytest.mark.critical
    async def test_success_returns_correlation_data(self) -> None:
        """Successful correlation returns formatted pair data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        # Mock OHLCV fetch for both tickers
        async def _mock_fetch(ticker: str, period: str = "1y") -> list[MagicMock]:
            if ticker == "AAPL":
                return _make_ohlcv_series(n=60, base_price=185.0)
            return _make_ohlcv_series(n=60, base_price=320.0)

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])

        assert "Correlation Matrix" in result
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid primary ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_correlation_matrix_tool(ctx, "!!BAD!!", ["MSFT"])

        assert result.startswith("Error:")
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_invalid_comparison_ticker_returns_error(self) -> None:
        """Invalid comparison ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["!!BAD!!"])

        assert result.startswith("Error:")
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_service_failure_returns_error(self) -> None:
        """Service error returns Error: string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network error"))

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])

        assert result.startswith("Error:")
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_caps_comparison_tickers(self) -> None:
        """More than 5 comparison tickers are capped to 5."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        tickers = ["MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AMD"]

        async def _mock_fetch(ticker: str, period: str = "1y") -> list[MagicMock]:
            return _make_ohlcv_series(n=60, base_price=100.0 + hash(ticker) % 100)

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", tickers)

        # Should succeed with capped tickers (5+1 primary)
        assert "Correlation Matrix" in result
        # Verify the 6th and 7th tickers were dropped
        assert "NVDA" not in result
        assert "AMD" not in result
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_primary_ticker_not_in_ohlcv_returns_error(self) -> None:
        """When primary ticker OHLCV fails, returns error."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        async def _mock_fetch(ticker: str, period: str = "1y") -> list[MagicMock]:
            if ticker == "AAPL":
                return []
            return _make_ohlcv_series(n=60, base_price=320.0)

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])

        assert "Error:" in result
        assert "compute_correlation_matrix" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_risk_adjusted_metrics_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRiskAdjustedMetricsTool:
    """Test the compute_risk_adjusted_metrics_tool wrapper."""

    async def test_success_returns_formatted_metrics(self) -> None:
        """Successful query returns formatted Sharpe/Sortino/drawdown."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.05)

        # Mock risk-adjusted metrics result
        mock_result = RiskAdjustedMetrics(
            lookback_days=365,
            total_trades=50,
            sharpe_ratio=1.25,
            sortino_ratio=1.80,
            max_drawdown_pct=15.3,
            max_drawdown_date=None,
            annualized_return_pct=22.5,
            risk_free_rate=0.05,
        )
        deps.repo.get_risk_adjusted_metrics = AsyncMock(return_value=mock_result)

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")

        assert "Risk-Adjusted Metrics" in result
        assert "Sharpe Ratio: 1.25" in result
        assert "Sortino Ratio: 1.80" in result
        assert "Max Drawdown: 15.3%" in result
        assert "Annualized Return: 22.5%" in result
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_no_outcomes_returns_message(self) -> None:
        """No outcomes returns informative message."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.05)

        mock_result = RiskAdjustedMetrics(
            lookback_days=365,
            total_trades=0,
            sharpe_ratio=None,
            sortino_ratio=None,
            max_drawdown_pct=None,
            max_drawdown_date=None,
            annualized_return_pct=None,
            risk_free_rate=0.05,
        )
        deps.repo.get_risk_adjusted_metrics = AsyncMock(return_value=mock_result)

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")

        assert "No outcome data" in result
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_risk_adjusted_metrics_tool(ctx, "!!BAD!!")

        assert result.startswith("Error:")
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_service_failure_returns_error(self) -> None:
        """Service error returns Error: string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_risk_adjusted_metrics = AsyncMock(side_effect=RuntimeError("db error"))

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")

        assert result.startswith("Error:")
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_fred_unavailable_uses_default_rate(self) -> None:
        """When FRED fails, tool still completes with default rate."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.fred.fetch_risk_free_rate = AsyncMock(side_effect=RuntimeError("FRED down"))

        mock_result = RiskAdjustedMetrics(
            lookback_days=365,
            total_trades=35,
            sharpe_ratio=0.85,
            sortino_ratio=1.10,
            max_drawdown_pct=20.0,
            max_drawdown_date=None,
            annualized_return_pct=12.0,
            risk_free_rate=0.05,
        )
        deps.repo.get_risk_adjusted_metrics = AsyncMock(return_value=mock_result)

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")

        assert "Risk-Adjusted Metrics" in result
        assert "compute_risk_adjusted_metrics" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: Tool annotations
# ---------------------------------------------------------------------------


class TestCorrelationRiskToolAnnotations:
    """Test that correlation/risk tools have correct signatures and are async."""

    def test_correlation_tool_is_async(self) -> None:
        """compute_correlation_matrix_tool is async."""
        assert inspect.iscoroutinefunction(compute_correlation_matrix_tool)

    def test_risk_metrics_tool_is_async(self) -> None:
        """compute_risk_adjusted_metrics_tool is async."""
        assert inspect.iscoroutinefunction(compute_risk_adjusted_metrics_tool)

    def test_correlation_tool_returns_str(self) -> None:
        """compute_correlation_matrix_tool returns str."""
        ret = compute_correlation_matrix_tool.__annotations__.get("return")
        assert ret == "str"

    def test_risk_metrics_tool_returns_str(self) -> None:
        """compute_risk_adjusted_metrics_tool returns str."""
        ret = compute_risk_adjusted_metrics_tool.__annotations__.get("return")
        assert ret == "str"

    def test_correlation_tool_signature(self) -> None:
        """compute_correlation_matrix_tool accepts ctx, ticker, comparison_tickers."""
        sig = inspect.signature(compute_correlation_matrix_tool)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker", "comparison_tickers"]

    def test_risk_metrics_tool_signature(self) -> None:
        """compute_risk_adjusted_metrics_tool accepts ctx and ticker."""
        sig = inspect.signature(compute_risk_adjusted_metrics_tool)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker"]
