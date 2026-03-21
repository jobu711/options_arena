"""Tests for macro regime and Hurst exponent tool wrappers.

Task #627: Verifies compute_macro_regime_tool and compute_hurst_exponent_tool
follow the never-raise contract, handle service unavailability, and format
output correctly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_hurst_exponent_tool,
    compute_macro_regime_tool,
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


def _make_ohlcv_series(n: int = 260, base_price: float = 100.0) -> list[MagicMock]:
    """Create a list of mock OHLCV bars with increasing dates."""
    bars: list[MagicMock] = []
    start_date = date(2025, 3, 1)
    for i in range(n):
        price = base_price + i * 0.1
        bar = MagicMock()
        bar.date = start_date + timedelta(days=i)
        bar.open = Decimal(str(price - 0.5))
        bar.high = Decimal(str(price + 1.0))
        bar.low = Decimal(str(price - 1.0))
        bar.close = Decimal(str(price))
        bar.volume = 1_000_000
        bars.append(bar)
    return bars


# ---------------------------------------------------------------------------
# Test: compute_macro_regime_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMacroRegimeTool:
    """Test the compute_macro_regime_tool wrapper."""

    @pytest.mark.critical
    async def test_macro_success_formats_regime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify macro tool returns formatted regime and confidence."""
        from options_arena.indicators.macro import MacroClassification
        from options_arena.models.enums import MacroRegime
        from options_arena.models.macro import MacroContext

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.040,
            yield_spread_10y2y=0.005,
            unemployment_rate=0.038,
            fed_funds_rate=0.0525,
            vix=15.5,
            cpi_yoy=2.8,
        )
        ctx.deps.fred.fetch_macro_context = AsyncMock(return_value=mock_macro)

        mock_result = MacroClassification(
            regime=MacroRegime.EXPANSIONARY,
            confidence=0.75,
        )
        monkeypatch.setattr(
            "options_arena.indicators.macro.compute_macro_regime",
            lambda **kw: mock_result,
        )

        result = await compute_macro_regime_tool(ctx)

        assert "Macro regime: expansionary" in result
        assert "75%" in result

    async def test_macro_fred_none_returns_unavailable(self) -> None:
        """Verify graceful message when fred service is None."""
        deps = _make_deps(fred=None)
        ctx = _make_mock_ctx(deps)

        result = await compute_macro_regime_tool(ctx)

        assert "not available" in result.lower()

    async def test_macro_returns_na_on_none_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns N/A when compute_macro_regime returns None."""
        from options_arena.models.macro import MacroContext

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        # All-None macro context → compute_macro_regime returns None
        mock_macro = MacroContext.fallback()
        ctx.deps.fred.fetch_macro_context = AsyncMock(return_value=mock_macro)

        monkeypatch.setattr(
            "options_arena.indicators.macro.compute_macro_regime",
            lambda **kw: None,
        )

        result = await compute_macro_regime_tool(ctx)

        assert "N/A" in result

    async def test_macro_tracks_tools_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool_name appended to tools_used."""
        from options_arena.indicators.macro import MacroClassification
        from options_arena.models.enums import MacroRegime
        from options_arena.models.macro import MacroContext

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_macro = MacroContext(yield_spread_10y2y=0.005, unemployment_rate=0.038)
        ctx.deps.fred.fetch_macro_context = AsyncMock(return_value=mock_macro)

        mock_result = MacroClassification(
            regime=MacroRegime.TRANSITIONAL,
            confidence=0.4,
        )
        monkeypatch.setattr(
            "options_arena.indicators.macro.compute_macro_regime",
            lambda **kw: mock_result,
        )

        await compute_macro_regime_tool(ctx)

        assert "compute_macro_regime" in ctx.deps.tools_used

    async def test_macro_exception_returns_error(self) -> None:
        """Verify never-raise contract on unexpected exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.fred.fetch_macro_context = AsyncMock(
            side_effect=RuntimeError("FRED down")
        )

        result = await compute_macro_regime_tool(ctx)

        assert "Error" in result or "error" in result.lower()


# ---------------------------------------------------------------------------
# Test: compute_hurst_exponent_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHurstExponentTool:
    """Test the compute_hurst_exponent_tool wrapper."""

    @pytest.mark.critical
    async def test_hurst_success_formats_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Hurst tool returns formatted H value and interpretation."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.65,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "Hurst exponent for AAPL" in result
        assert "0.650" in result
        assert "trending" in result.lower()

    async def test_hurst_trending_interpretation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify H > 0.55 is labeled 'trending'."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.70,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "trending" in result.lower()

    async def test_hurst_mean_reverting_interpretation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify H < 0.45 is labeled 'mean-reverting'."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.35,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "mean-reverting" in result.lower()

    async def test_hurst_random_walk_interpretation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify H ~ 0.5 is labeled 'random walk'."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.50,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "random walk" in result.lower()

    async def test_hurst_returns_na_on_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns N/A when hurst_exponent returns None."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: None,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "N/A" in result

    async def test_hurst_invalid_ticker(self) -> None:
        """Verify _validate_ticker rejects bad ticker."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_hurst_exponent_tool(ctx, "BAD!!!")

        assert "Error" in result
        assert "invalid ticker" in result.lower()

    async def test_hurst_empty_ohlcv(self) -> None:
        """Verify graceful handling when no OHLCV data returned."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "No OHLCV data" in result

    async def test_hurst_tracks_tools_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool_name appended to tools_used."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.55,
        )

        await compute_hurst_exponent_tool(ctx, "AAPL")

        assert "compute_hurst_exponent" in ctx.deps.tools_used
