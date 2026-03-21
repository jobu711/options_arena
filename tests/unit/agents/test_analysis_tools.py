"""Tests for valuation and position sizing tool wrappers."""

from __future__ import annotations

import inspect
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_composite_valuation_tool,
    compute_position_size_tool,
)

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


def _make_mock_ticker_info(
    ticker: str = "AAPL",
    current_price: str = "185.50",
    fifty_two_week_high: str = "199.62",
    fifty_two_week_low: str = "164.08",
) -> MagicMock:
    """Create a mock TickerInfo object."""
    info = MagicMock()
    info.ticker = ticker
    info.current_price = Decimal(current_price)
    info.fifty_two_week_high = Decimal(fifty_two_week_high)
    info.fifty_two_week_low = Decimal(fifty_two_week_low)
    return info


# ---------------------------------------------------------------------------
# Test: compute_composite_valuation_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCompositeValuationTool:
    """Test the compute_composite_valuation_tool wrapper."""

    @pytest.mark.critical
    async def test_success_returns_formatted_string(self) -> None:
        """Successful valuation returns string with price and signal info."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        result = await compute_composite_valuation_tool(ctx, "AAPL")

        assert "Composite Valuation" in result
        assert "AAPL" in result
        assert "Current Price:" in result
        assert "compute_composite_valuation" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_composite_valuation_tool(ctx, "!!INVALID!!")

        assert result.startswith("Error:")
        assert "compute_composite_valuation" in deps.tools_used

    async def test_service_failure_returns_error(self) -> None:
        """Service error returns Error: string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(
            side_effect=RuntimeError("connection failed")
        )

        result = await compute_composite_valuation_tool(ctx, "AAPL")

        assert result.startswith("Error:")
        assert "AAPL" in result
        assert "compute_composite_valuation" in deps.tools_used

    async def test_fred_unavailable_uses_default_rate(self) -> None:
        """When FRED fails, tool still completes with default rate."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(side_effect=RuntimeError("FRED down"))

        result = await compute_composite_valuation_tool(ctx, "AAPL")

        assert "Composite Valuation" in result
        assert "compute_composite_valuation" in deps.tools_used

    async def test_fred_none_uses_default_rate(self) -> None:
        """When FRED service is None, tool still completes with default rate."""
        deps = _make_deps(fred=None)
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())

        result = await compute_composite_valuation_tool(ctx, "AAPL")

        assert "Composite Valuation" in result
        assert "compute_composite_valuation" in deps.tools_used

    async def test_result_contains_signal_info(self) -> None:
        """Result includes fair value and signal fields."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.04)

        result = await compute_composite_valuation_tool(ctx, "AAPL")

        # With sparse FDData, most models return N/A
        assert "Fair Value:" in result
        assert "Signal:" in result


# ---------------------------------------------------------------------------
# Test: compute_position_size_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPositionSizeTool:
    """Test the compute_position_size_tool wrapper."""

    async def test_success_low_iv(self) -> None:
        """Low IV returns tier 1 with full allocation."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", 0.10)

        assert "Position Sizing" in result
        assert "AAPL" in result
        assert "Tier: 1" in result
        assert "low" in result.lower()
        assert "compute_position_size" in deps.tools_used

    async def test_success_high_iv(self) -> None:
        """High IV returns tier 4 with reduced allocation."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", 0.55)

        assert "Position Sizing" in result
        assert "Tier: 4" in result
        assert "extreme" in result.lower()
        assert "compute_position_size" in deps.tools_used

    async def test_with_correlation_adjustment(self) -> None:
        """Correlation above threshold applies penalty."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", 0.20, correlation=0.85)

        assert "Position Sizing" in result
        assert "Correlation Adjustment: 50%" in result
        assert "compute_position_size" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "!!INVALID!!", 0.25)

        assert result.startswith("Error:")
        assert "compute_position_size" in deps.tools_used

    async def test_nan_iv_returns_tier4(self) -> None:
        """NaN IV defaults to tier 4 (safest)."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", float("nan"))

        assert "Tier: 4" in result
        assert "compute_position_size" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: Tool annotations
# ---------------------------------------------------------------------------


class TestAnalysisToolAnnotations:
    """Test that analysis tools have correct signatures and are async."""

    def test_valuation_tool_is_async(self) -> None:
        """compute_composite_valuation_tool is async."""
        assert inspect.iscoroutinefunction(compute_composite_valuation_tool)

    def test_position_size_tool_is_async(self) -> None:
        """compute_position_size_tool is async."""
        assert inspect.iscoroutinefunction(compute_position_size_tool)

    def test_valuation_tool_returns_str(self) -> None:
        """compute_composite_valuation_tool returns str."""
        ret = compute_composite_valuation_tool.__annotations__.get("return")
        assert ret == "str"

    def test_position_size_tool_returns_str(self) -> None:
        """compute_position_size_tool returns str."""
        ret = compute_position_size_tool.__annotations__.get("return")
        assert ret == "str"

    def test_valuation_tool_signature(self) -> None:
        """compute_composite_valuation_tool accepts ctx and ticker."""
        sig = inspect.signature(compute_composite_valuation_tool)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker"]

    def test_position_size_tool_signature(self) -> None:
        """compute_position_size_tool accepts ctx, ticker, annualized_iv, correlation."""
        sig = inspect.signature(compute_position_size_tool)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker", "annualized_iv", "correlation"]
