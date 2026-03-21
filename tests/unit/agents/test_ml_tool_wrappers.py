"""Tests for GARCH forecast and Markov regime tool wrappers.

Task #626: Verifies compute_garch_forecast_tool and compute_markov_regime_tool
follow the never-raise contract, validate tickers, handle ImportError gracefully,
and format output correctly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_garch_forecast_tool,
    compute_markov_regime_tool,
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
# Test: compute_garch_forecast_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGARCHForecastTool:
    """Test the compute_garch_forecast_tool wrapper."""

    @pytest.mark.critical
    async def test_garch_success_formats_correctly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify GARCH tool returns formatted annualized vol string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        # Mock the indicator function to return a known value
        monkeypatch.setattr(
            "options_arena.indicators.vol_forecast.compute_garch_forecast",
            lambda returns, **kw: 0.25,
        )

        result = await compute_garch_forecast_tool(ctx, "AAPL")

        assert "GARCH(1,1) forecast for AAPL" in result
        assert "25.0%" in result
        assert "moderate volatility" in result

    async def test_garch_returns_na_on_none_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns N/A when compute_garch_forecast returns None."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.vol_forecast.compute_garch_forecast",
            lambda returns, **kw: None,
        )

        result = await compute_garch_forecast_tool(ctx, "AAPL")

        assert "N/A" in result
        assert "AAPL" in result

    async def test_garch_import_error_graceful(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns unavailable message when arch not installed."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        # Simulate ImportError by patching the import
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "options_arena.indicators.vol_forecast":
                raise ImportError("No module named 'arch'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        result = await compute_garch_forecast_tool(ctx, "AAPL")

        assert "unavailable" in result.lower() or "not installed" in result.lower()

    async def test_garch_invalid_ticker(self) -> None:
        """Verify _validate_ticker rejects bad ticker."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_garch_forecast_tool(ctx, "!!!INVALID!!!")

        assert "Error" in result
        assert "invalid ticker" in result.lower()

    async def test_garch_tracks_tools_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool_name appended to ctx.deps.tools_used."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.vol_forecast.compute_garch_forecast",
            lambda returns, **kw: 0.30,
        )

        await compute_garch_forecast_tool(ctx, "AAPL")

        assert "compute_garch_forecast" in ctx.deps.tools_used

    async def test_garch_empty_ohlcv(self) -> None:
        """Verify graceful handling when no OHLCV data returned."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_garch_forecast_tool(ctx, "AAPL")

        assert "No OHLCV data" in result


# ---------------------------------------------------------------------------
# Test: compute_markov_regime_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkovRegimeTool:
    """Test the compute_markov_regime_tool wrapper."""

    @pytest.mark.critical
    async def test_markov_success_formats_regime(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify Markov tool returns formatted regime label and probabilities."""
        from options_arena.indicators.regime_ml import MarkovRegimeOutput

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        mock_output = MarkovRegimeOutput(
            current_regime=1,
            regime_probabilities=[0.15, 0.70, 0.15],
            transition_matrix=[
                [0.90, 0.08, 0.02],
                [0.05, 0.85, 0.10],
                [0.03, 0.12, 0.85],
            ],
            regime_label="normal",
        )

        monkeypatch.setattr(
            "options_arena.indicators.regime_ml.compute_markov_regime",
            lambda returns, **kw: mock_output,
        )

        result = await compute_markov_regime_tool(ctx, "AAPL")

        assert "Markov regime for AAPL" in result
        assert "normal" in result
        assert "70.0%" in result

    async def test_markov_returns_na_on_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns N/A when compute_markov_regime returns None."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        monkeypatch.setattr(
            "options_arena.indicators.regime_ml.compute_markov_regime",
            lambda returns, **kw: None,
        )

        result = await compute_markov_regime_tool(ctx, "AAPL")

        assert "N/A" in result

    async def test_markov_import_error_graceful(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool returns unavailable message when statsmodels not installed."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "options_arena.indicators.regime_ml":
                raise ImportError("No module named 'statsmodels'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        result = await compute_markov_regime_tool(ctx, "AAPL")

        assert "unavailable" in result.lower() or "not installed" in result.lower()

    async def test_markov_invalid_ticker(self) -> None:
        """Verify _validate_ticker rejects bad ticker."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_markov_regime_tool(ctx, "!!!BAD!!!")

        assert "Error" in result
        assert "invalid ticker" in result.lower()

    async def test_markov_tracks_tools_used(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify tool_name appended to ctx.deps.tools_used."""
        from options_arena.indicators.regime_ml import MarkovRegimeOutput

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(
            return_value=_make_ohlcv_series(260)
        )

        mock_output = MarkovRegimeOutput(
            current_regime=0,
            regime_probabilities=[0.80, 0.15, 0.05],
            transition_matrix=[
                [0.90, 0.08, 0.02],
                [0.05, 0.85, 0.10],
                [0.03, 0.12, 0.85],
            ],
            regime_label="low_vol",
        )

        monkeypatch.setattr(
            "options_arena.indicators.regime_ml.compute_markov_regime",
            lambda returns, **kw: mock_output,
        )

        await compute_markov_regime_tool(ctx, "AAPL")

        assert "compute_markov_regime" in ctx.deps.tools_used

    async def test_markov_empty_ohlcv(self) -> None:
        """Verify graceful handling when no OHLCV data returned."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_markov_regime_tool(ctx, "AAPL")

        assert "No OHLCV data" in result
