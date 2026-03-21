"""Integration tests for ML tool wrappers and toolset degradation.

Task #629: Verifies end-to-end tool execution with mocked services,
toolset degradation when [ml] not installed, and render_available_tools
integration with real toolsets.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    build_contrarian_toolset,
    build_flow_toolset,
    build_fundamental_toolset,
    build_research_toolset,
    build_risk_toolset,
    build_trend_toolset,
    build_volatility_toolset,
    compute_garch_forecast_tool,
    compute_hurst_exponent_tool,
    compute_macro_regime_tool,
    compute_markov_regime_tool,
    render_available_tools,
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


def _hide_package(
    monkeypatch: pytest.MonkeyPatch,
    package_name: str,
) -> None:
    """Make ``import <package_name>`` raise ImportError."""
    import builtins

    original_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == package_name or name.startswith(package_name + "."):
            raise ImportError(f"Mocked: No module named {package_name!r}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)


# ---------------------------------------------------------------------------
# Toolset Degradation — parametrized across desks
# ---------------------------------------------------------------------------


class TestToolsetDegradation:
    """All desks build valid toolsets with and without [ml]."""

    _ALL_DESKS = [
        "volatility",
        "trend",
        "fundamental",
        "risk",
        "research",
        "flow",
        "contrarian",
    ]

    _DESK_BUILDERS = {
        "volatility": build_volatility_toolset,
        "trend": build_trend_toolset,
        "fundamental": build_fundamental_toolset,
        "risk": build_risk_toolset,
        "research": build_research_toolset,
        "flow": build_flow_toolset,
        "contrarian": build_contrarian_toolset,
    }

    @pytest.mark.parametrize("desk", _ALL_DESKS)
    def test_toolset_builds_with_ml(self, desk: str) -> None:
        """All desks build valid (non-empty) toolsets when [ml] installed."""
        builder = self._DESK_BUILDERS[desk]
        tools = builder()

        assert isinstance(tools, list)
        assert len(tools) > 0

    @pytest.mark.parametrize("desk", ["volatility", "trend", "risk", "research"])
    def test_toolset_builds_without_ml(self, desk: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Affected desks build toolsets without [ml] (fewer tools)."""
        _hide_package(monkeypatch, "arch")
        _hide_package(monkeypatch, "statsmodels")

        builder = self._DESK_BUILDERS[desk]
        tools = builder()

        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_flow_unaffected_by_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Flow desk has same tools with or without [ml]."""
        tools_with = build_flow_toolset()

        _hide_package(monkeypatch, "arch")
        _hide_package(monkeypatch, "statsmodels")
        tools_without = build_flow_toolset()

        assert len(tools_with) == len(tools_without)

    def test_contrarian_unaffected_by_ml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Contrarian desk has same tools with or without [ml]."""
        tools_with = build_contrarian_toolset()

        _hide_package(monkeypatch, "arch")
        _hide_package(monkeypatch, "statsmodels")
        tools_without = build_contrarian_toolset()

        assert len(tools_with) == len(tools_without)

    def test_partial_ml_arch_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Desks degrade correctly when only statsmodels is missing."""
        _hide_package(monkeypatch, "statsmodels")

        # Volatility should still have GARCH (needs arch, not statsmodels)
        vol_tools = build_volatility_toolset()
        try:
            import arch  # noqa: F401

            assert compute_garch_forecast_tool in vol_tools
        except ImportError:
            pass

        # Trend should lose Markov but keep Hurst
        trend_tools = build_trend_toolset()
        assert compute_hurst_exponent_tool in trend_tools
        assert compute_markov_regime_tool not in trend_tools

    def test_partial_ml_statsmodels_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Desks degrade correctly when only arch is missing."""
        _hide_package(monkeypatch, "arch")

        # Volatility should lose GARCH
        vol_tools = build_volatility_toolset()
        assert compute_garch_forecast_tool not in vol_tools

        # Trend should still have Markov (needs statsmodels, not arch)
        trend_tools = build_trend_toolset()
        try:
            import statsmodels  # noqa: F401

            assert compute_markov_regime_tool in trend_tools
        except ImportError:
            pass


# ---------------------------------------------------------------------------
# End-to-End tool execution with mocked services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMLToolEndToEnd:
    """End-to-end tool execution with realistic mocked data."""

    @pytest.mark.critical
    async def test_garch_full_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GARCH tool: OHLCV -> returns -> forecast -> formatted string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(260))

        monkeypatch.setattr(
            "options_arena.indicators.vol_forecast.compute_garch_forecast",
            lambda returns, **kw: 0.22,
        )

        result = await compute_garch_forecast_tool(ctx, "AAPL")

        assert isinstance(result, str)
        assert "GARCH" in result
        assert "AAPL" in result
        assert "22.0%" in result
        assert "compute_garch_forecast" in ctx.deps.tools_used

    @pytest.mark.critical
    async def test_markov_full_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Markov tool: OHLCV -> returns -> regime -> formatted string."""
        from options_arena.indicators.regime_ml import MarkovRegimeOutput

        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(260))

        mock_output = MarkovRegimeOutput(
            current_regime=2,
            regime_probabilities=[0.05, 0.10, 0.85],
            transition_matrix=[
                [0.90, 0.08, 0.02],
                [0.05, 0.85, 0.10],
                [0.03, 0.12, 0.85],
            ],
            regime_label="high_vol",
        )
        monkeypatch.setattr(
            "options_arena.indicators.regime_ml.compute_markov_regime",
            lambda returns, **kw: mock_output,
        )

        result = await compute_markov_regime_tool(ctx, "AAPL")

        assert isinstance(result, str)
        assert "Markov regime for AAPL" in result
        assert "high_vol" in result
        assert "85.0%" in result
        assert "compute_markov_regime" in ctx.deps.tools_used

    @pytest.mark.critical
    async def test_macro_full_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Macro tool: FRED context -> regime -> formatted string."""
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
            confidence=0.8,
        )
        monkeypatch.setattr(
            "options_arena.indicators.macro.compute_macro_regime",
            lambda **kw: mock_result,
        )

        result = await compute_macro_regime_tool(ctx)

        assert isinstance(result, str)
        assert "expansionary" in result
        assert "80%" in result
        assert "Yield spread" in result
        assert "compute_macro_regime" in ctx.deps.tools_used

    @pytest.mark.critical
    async def test_hurst_full_pipeline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hurst tool: OHLCV -> close Series -> H value -> formatted string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        ctx.deps.market_data.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv_series(260))

        monkeypatch.setattr(
            "options_arena.indicators.hurst.hurst_exponent",
            lambda close, **kw: 0.62,
        )

        result = await compute_hurst_exponent_tool(ctx, "AAPL")

        assert isinstance(result, str)
        assert "Hurst exponent for AAPL" in result
        assert "0.620" in result
        assert "trending" in result.lower()
        assert "compute_hurst_exponent" in ctx.deps.tools_used


# ---------------------------------------------------------------------------
# render_available_tools integration with real toolsets
# ---------------------------------------------------------------------------


class TestRenderAvailableToolsIntegration:
    """render_available_tools output matches build_*_toolset() tools."""

    @pytest.mark.parametrize(
        "desk",
        ["volatility", "trend", "fundamental", "risk", "research"],
    )
    def test_render_matches_toolset(self, desk: str) -> None:
        """render_available_tools output matches build_*_toolset() tools."""
        builders = {
            "volatility": build_volatility_toolset,
            "trend": build_trend_toolset,
            "fundamental": build_fundamental_toolset,
            "risk": build_risk_toolset,
            "research": build_research_toolset,
        }
        tools = builders[desk]()
        result = render_available_tools(tools)

        # Each tool name should appear in the rendered output
        for tool in tools:
            name = getattr(tool, "__name__", str(tool))
            assert name in result, f"Tool {name} missing from render output for {desk}"

    def test_render_contains_delimiters(self) -> None:
        """Output starts with <<<AVAILABLE_TOOLS>>> and ends correctly."""
        tools = build_fundamental_toolset()
        result = render_available_tools(tools)

        lines = result.strip().split("\n")
        assert lines[0] == "<<<AVAILABLE_TOOLS>>>"
        assert lines[-1] == "<<<END_AVAILABLE_TOOLS>>>"
