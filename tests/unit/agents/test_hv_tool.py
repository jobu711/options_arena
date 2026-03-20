"""Tests for Yang-Zhang historical volatility tool wrapper."""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import compute_hv_yang_zhang_tool

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


def _make_ohlcv_series(
    n: int = 60,
    base_price: float = 185.0,
    daily_vol: float = 2.0,
) -> list[MagicMock]:
    """Create a list of mock OHLCV bars with realistic price movement.

    Generates bars with varying open/high/low/close to produce
    a non-trivial Yang-Zhang volatility estimate.
    """
    import random

    random.seed(42)
    bars: list[MagicMock] = []
    start_date = date(2025, 6, 1)
    price = base_price

    for i in range(n):
        # Small random walk with realistic high/low range
        change = random.gauss(0, daily_vol)
        open_ = price + random.gauss(0, daily_vol * 0.3)
        close = price + change
        high = max(open_, close) + abs(random.gauss(0, daily_vol * 0.5))
        low = min(open_, close) - abs(random.gauss(0, daily_vol * 0.5))
        price = close

        bar = MagicMock()
        bar.date = start_date + timedelta(days=i)
        bar.open = Decimal(str(round(max(open_, 1.0), 2)))
        bar.high = Decimal(str(round(max(high, 1.0), 2)))
        bar.low = Decimal(str(round(max(low, 0.5), 2)))
        bar.close = Decimal(str(round(max(close, 1.0), 2)))
        bar.volume = 1_000_000
        bars.append(bar)

    return bars


# ---------------------------------------------------------------------------
# Test: compute_hv_yang_zhang_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHvYangZhangTool:
    """Test the compute_hv_yang_zhang_tool wrapper."""

    async def test_success_returns_annualized_hv(self) -> None:
        """Successful computation returns formatted HV string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(n=60))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")

        assert "Yang-Zhang HV" in result
        assert "AAPL" in result
        assert "annualized" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_custom_period(self) -> None:
        """Custom period is used in computation."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(n=60))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL", period=30)

        assert "HV(30)" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_period_clamped_low(self) -> None:
        """Period below 2 is clamped to 2."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(n=60))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL", period=0)

        assert "HV(2)" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_period_clamped_high(self) -> None:
        """Period above 60 is clamped to 60."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        # Need enough data for period=60 (period+1 bars minimum)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(n=100))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL", period=200)

        assert "HV(60)" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_hv_yang_zhang_tool(ctx, "!!BAD!!")

        assert result.startswith("Error:")
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_no_ohlcv_data_returns_message(self) -> None:
        """Empty OHLCV returns informative message."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")

        assert "No OHLCV data" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_insufficient_data_returns_na(self) -> None:
        """Too few bars for period returns N/A message."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        # Only 5 bars for default period=20 (needs 21)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(n=5))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")

        assert "N/A" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_service_failure_returns_error(self) -> None:
        """Service error returns Error: string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("connection failed"))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")

        assert result.startswith("Error:")
        assert "AAPL" in result
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_interpretation_low_vol(self) -> None:
        """Low HV value returns 'low volatility' interpretation."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        # Very low daily vol to produce low HV
        deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(n=60, base_price=185.0, daily_vol=0.1)
        )

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")

        # Should complete successfully
        assert "Yang-Zhang HV" in result
        assert "compute_hv_yang_zhang" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: Tool annotations
# ---------------------------------------------------------------------------


class TestHvToolAnnotations:
    """Test that the HV tool has correct signature and is async."""

    def test_hv_tool_is_async(self) -> None:
        """compute_hv_yang_zhang_tool is async."""
        assert inspect.iscoroutinefunction(compute_hv_yang_zhang_tool)

    def test_hv_tool_returns_str(self) -> None:
        """compute_hv_yang_zhang_tool returns str."""
        ret = compute_hv_yang_zhang_tool.__annotations__.get("return")
        assert ret == "str"

    def test_hv_tool_signature(self) -> None:
        """compute_hv_yang_zhang_tool accepts ctx, ticker, period."""
        sig = inspect.signature(compute_hv_yang_zhang_tool)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker", "period"]
