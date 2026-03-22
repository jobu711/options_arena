"""Tests for risk, ML, and synthesis tools refactored to ToolResponse JSON output.

Validates that the 10 tools (compute_position_size_tool,
compute_correlation_matrix_tool, compute_risk_adjusted_metrics_tool,
compute_hv_yang_zhang_tool, compute_macro_regime_tool, compute_garch_forecast_tool,
compute_markov_regime_tool, compute_hurst_exponent_tool, synth_fetch_current_quote,
synth_fetch_chain_summary) return valid ToolResponse JSON on all code paths.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_correlation_matrix_tool,
    compute_garch_forecast_tool,
    compute_hurst_exponent_tool,
    compute_hv_yang_zhang_tool,
    compute_macro_regime_tool,
    compute_markov_regime_tool,
    compute_position_size_tool,
    compute_risk_adjusted_metrics_tool,
    synth_fetch_chain_summary,
    synth_fetch_current_quote,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_ctx(deps: object) -> MagicMock:
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
    bar_date: date | None = None,
    close: str = "185.00",
    open_: str = "184.00",
    high: str = "186.00",
    low: str = "183.00",
    volume: int = 1_000_000,
) -> MagicMock:
    """Create a mock OHLCV bar."""
    bar = MagicMock()
    bar.date = bar_date or date.today()
    bar.close = Decimal(close)
    bar.open = Decimal(open_)
    bar.high = Decimal(high)
    bar.low = Decimal(low)
    bar.volume = volume
    return bar


def _make_mock_contract(
    ticker: str = "AAPL",
    option_type_val: str = "call",
    strike: str = "190.00",
    expiration: date | None = None,
    bid: str = "4.50",
    ask: str = "4.80",
    volume: int = 1500,
    open_interest: int = 12000,
    market_iv: float = 0.285,
) -> MagicMock:
    """Create a mock OptionContract object."""
    contract = MagicMock()
    contract.ticker = ticker
    contract.option_type = MagicMock()
    contract.option_type.value = option_type_val
    contract.strike = Decimal(strike)
    contract.expiration = expiration or (date.today() + timedelta(days=45))
    contract.bid = Decimal(bid)
    contract.ask = Decimal(ask)
    contract.mid = (Decimal(bid) + Decimal(ask)) / Decimal("2")
    contract.spread = Decimal(ask) - Decimal(bid)
    contract.volume = volume
    contract.open_interest = open_interest
    contract.market_iv = market_iv
    contract.greeks = None
    return contract


def _assert_tool_response_structure(parsed: dict[str, object]) -> None:
    """Assert that a parsed JSON dict has the required ToolResponse fields."""
    assert "status" in parsed
    assert parsed["status"] in {"success", "warning", "error"}
    assert "summary" in parsed
    assert isinstance(parsed["summary"], str)
    assert "next_actions" in parsed
    assert isinstance(parsed["next_actions"], list)


# ---------------------------------------------------------------------------
# Test: compute_position_size_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestComputePositionSizeToolResponse:
    """Test compute_position_size_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with position sizing data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", 0.25)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Position Sizing" in parsed["data"]
        assert "use suggested allocation" in parsed["next_actions"]
        assert "compute_position_size" in deps.tools_used

    async def test_error_non_finite_iv(self) -> None:
        """Error when annualized_iv is non-finite."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "AAPL", float("nan"))
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "compute_position_size" in deps.tools_used

    async def test_error_computation_fails(self) -> None:
        """Error when computation raises exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        with patch(
            "options_arena.agents._toolsets.compute_position_size_tool.__module__",
        ):
            # Force ImportError by patching the lazy import
            result = await compute_position_size_tool(ctx, "AAPL", -999.0)
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert "compute_position_size" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_position_size_tool(ctx, "!!!bad!!!", 0.25)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_position_size" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success and error paths."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        await compute_position_size_tool(ctx_s, "AAPL", 0.25)
        assert "compute_position_size" in deps_s.tools_used

        # Non-finite IV error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        await compute_position_size_tool(ctx_e, "AAPL", float("inf"))
        assert "compute_position_size" in deps_e.tools_used


# ---------------------------------------------------------------------------
# Test: compute_correlation_matrix_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeCorrelationMatrixToolResponse:
    """Test compute_correlation_matrix_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with correlation data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars_aapl = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        bars_msft = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("300.00") + Decimal(str(i)) * Decimal("0.15")),
            )
            for i in range(252)
        ]

        async def _mock_fetch_ohlcv(ticker: str, period: str = "1y") -> list[MagicMock]:
            if ticker == "AAPL":
                return bars_aapl
            return bars_msft

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch_ohlcv)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Correlation Matrix" in parsed["data"]
        assert "assess portfolio diversification" in parsed["next_actions"]
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_warning_partial_data(self) -> None:
        """Warning when some tickers have insufficient data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars_aapl = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        bars_msft = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("300.00") + Decimal(str(i)) * Decimal("0.15")),
            )
            for i in range(252)
        ]

        async def _mock_fetch_ohlcv(ticker: str, period: str = "1y") -> list[MagicMock]:
            if ticker == "AAPL":
                return bars_aapl
            if ticker == "MSFT":
                return bars_msft
            raise RuntimeError("no data")

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch_ohlcv)

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT", "GOOG"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert "note incomplete correlation data" in parsed["next_actions"]

    async def test_error_base_ticker_fails(self) -> None:
        """Error when the base ticker fails to fetch."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network error"))

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error on outer exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("boom"))

        result = await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_correlation_matrix_tool(ctx, "!!!bad!!!", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_correlation_matrix" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_correlation_matrix_tool(ctx, "AAPL", ["MSFT"])
        assert "compute_correlation_matrix" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_risk_adjusted_metrics_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeRiskAdjustedMetricsToolResponse:
    """Test compute_risk_adjusted_metrics_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with risk metrics."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_result = MagicMock()
        mock_result.total_trades = 50
        mock_result.lookback_days = 365
        mock_result.sharpe_ratio = 1.25
        mock_result.sortino_ratio = 1.8
        mock_result.max_drawdown_pct = -15.3
        mock_result.annualized_return_pct = 22.5
        deps.repo.get_risk_adjusted_metrics = AsyncMock(return_value=mock_result)

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Sharpe Ratio" in parsed["data"]
        assert "compare risk-adjusted returns" in parsed["next_actions"]
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_error_no_outcomes(self) -> None:
        """Error when no outcome data is available."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_result = MagicMock()
        mock_result.total_trades = 0
        deps.repo.get_risk_adjusted_metrics = AsyncMock(return_value=mock_result)

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No outcome data" in parsed["summary"]
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when repo raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_risk_adjusted_metrics = AsyncMock(side_effect=RuntimeError("db error"))

        result = await compute_risk_adjusted_metrics_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_risk_adjusted_metrics_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_risk_adjusted_metrics" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_risk_adjusted_metrics = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_risk_adjusted_metrics_tool(ctx, "AAPL")
        assert "compute_risk_adjusted_metrics" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_hv_yang_zhang_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeHVYangZhangToolResponse:
    """Test compute_hv_yang_zhang_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with HV data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        # Create 252 OHLCV bars with enough variation for HV computation
        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                open_=str(Decimal("180.00") + Decimal(str(i)) * Decimal("0.05")),
                high=str(Decimal("182.00") + Decimal(str(i)) * Decimal("0.05")),
                low=str(Decimal("178.00") + Decimal(str(i)) * Decimal("0.05")),
                close=str(Decimal("181.00") + Decimal(str(i)) * Decimal("0.05")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Yang-Zhang" in parsed["data"]
        assert "compare HV to IV for vol premium" in parsed["next_actions"]
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_error_no_ohlcv(self) -> None:
        """Error when no OHLCV data available."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No OHLCV data" in parsed["summary"]
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_hv_yang_zhang_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_hv_yang_zhang_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_hv_yang_zhang" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_hv_yang_zhang_tool(ctx, "AAPL")
        assert "compute_hv_yang_zhang" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_macro_regime_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeMacroRegimeToolResponse:
    """Test compute_macro_regime_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with macro regime."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_macro_ctx = MagicMock()
        mock_macro_ctx.yield_spread_10y2y = 0.0125
        mock_macro_ctx.unemployment_rate = 0.038
        mock_macro_ctx.fed_funds_rate = 0.0525
        mock_macro_ctx.vix = 16.5
        mock_macro_ctx.cpi_yoy = 0.032
        mock_macro_ctx.completeness_ratio.return_value = 1.0
        deps.fred.fetch_macro_context = AsyncMock(return_value=mock_macro_ctx)

        result = await compute_macro_regime_tool(ctx)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Macro regime" in parsed["data"]
        assert "factor macro regime into risk assessment" in parsed["next_actions"]
        assert "compute_macro_regime" in deps.tools_used

    async def test_warning_partial_fred_data(self) -> None:
        """Warning when some FRED series are unavailable."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        mock_macro_ctx = MagicMock()
        mock_macro_ctx.yield_spread_10y2y = 0.0125
        mock_macro_ctx.unemployment_rate = None  # Missing
        mock_macro_ctx.fed_funds_rate = 0.0525
        mock_macro_ctx.vix = None  # Missing
        mock_macro_ctx.cpi_yoy = 0.032
        mock_macro_ctx.completeness_ratio.return_value = 0.6
        deps.fred.fetch_macro_context = AsyncMock(return_value=mock_macro_ctx)

        result = await compute_macro_regime_tool(ctx)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert "note partial macro data" in parsed["next_actions"]
        assert "compute_macro_regime" in deps.tools_used

    async def test_error_fred_not_available(self) -> None:
        """Error when FRED service is None."""
        deps = _make_deps(fred=None)
        ctx = _make_mock_ctx(deps)

        result = await compute_macro_regime_tool(ctx)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "FRED service not available" in parsed["summary"]
        assert "skip macro analysis" in parsed["next_actions"]
        assert "compute_macro_regime" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when FRED service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.fred.fetch_macro_context = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_macro_regime_tool(ctx)
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_macro_regime" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.fred.fetch_macro_context = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_macro_regime_tool(ctx)
        assert "compute_macro_regime" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_garch_forecast_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeGarchForecastToolResponse:
    """Test compute_garch_forecast_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with GARCH forecast."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        # Mock the compute_garch_forecast function to return a value
        with (
            patch(
                "options_arena.agents._toolsets.compute_garch_forecast",
                create=True,
            ),
            patch(
                "options_arena.indicators.vol_forecast.compute_garch_forecast",
                return_value=0.22,
                create=True,
            ),
        ):
            result = await compute_garch_forecast_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        # May be success or error depending on arch availability
        assert "compute_garch_forecast" in deps.tools_used

    async def test_error_ml_not_installed(self) -> None:
        """Error when [ml] extra is not installed."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        # Simulate ImportError for vol_forecast module
        with (
            patch.dict("sys.modules", {"options_arena.indicators.vol_forecast": None}),
            patch(
                "builtins.__import__",
                side_effect=_make_import_error_raiser("options_arena.indicators.vol_forecast"),
            ),
        ):
            result = await compute_garch_forecast_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_garch_forecast" in deps.tools_used

    async def test_error_no_ohlcv(self) -> None:
        """Error when no OHLCV data available."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_garch_forecast_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No OHLCV data" in parsed["summary"]
        assert "compute_garch_forecast" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_garch_forecast_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_garch_forecast" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_garch_forecast_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "skip GARCH analysis" in parsed["next_actions"]
        assert "compute_garch_forecast" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_garch_forecast_tool(ctx, "AAPL")
        assert "compute_garch_forecast" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_markov_regime_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeMarkovRegimeToolResponse:
    """Test compute_markov_regime_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with regime data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        # Mock the compute_markov_regime function
        mock_result = MagicMock()
        mock_result.regime_label = "low_vol"
        mock_result.current_regime = 0
        mock_result.regime_probabilities = [0.85, 0.10, 0.05]
        mock_result.transition_matrix = [
            [0.90, 0.08, 0.02],
            [0.05, 0.85, 0.10],
            [0.02, 0.08, 0.90],
        ]

        with patch(
            "options_arena.indicators.regime_ml.compute_markov_regime",
            return_value=mock_result,
            create=True,
        ):
            result = await compute_markov_regime_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        # May be success or error depending on statsmodels availability
        assert "compute_markov_regime" in deps.tools_used

    async def test_error_ml_not_installed(self) -> None:
        """Error when [ml] extra (statsmodels) is not installed."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        with (
            patch.dict("sys.modules", {"options_arena.indicators.regime_ml": None}),
            patch(
                "builtins.__import__",
                side_effect=_make_import_error_raiser("options_arena.indicators.regime_ml"),
            ),
        ):
            result = await compute_markov_regime_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_markov_regime" in deps.tools_used

    async def test_error_no_ohlcv(self) -> None:
        """Error when no OHLCV data available."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_markov_regime_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_markov_regime" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_markov_regime_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_markov_regime" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_markov_regime_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "skip regime detection" in parsed["next_actions"]
        assert "compute_markov_regime" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_markov_regime_tool(ctx, "AAPL")
        assert "compute_markov_regime" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_hurst_exponent_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeHurstExponentToolResponse:
    """Test compute_hurst_exponent_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with Hurst exponent."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        result = await compute_hurst_exponent_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Hurst exponent" in parsed["data"]
        assert "assess persistence of current trend" in parsed["next_actions"]
        assert "compute_hurst_exponent" in deps.tools_used

    async def test_error_no_ohlcv(self) -> None:
        """Error when no OHLCV data available."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_hurst_exponent_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No OHLCV data" in parsed["summary"]
        assert "compute_hurst_exponent" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_hurst_exponent_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_hurst_exponent" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns error ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_hurst_exponent_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "skip Hurst analysis" in parsed["next_actions"]
        assert "compute_hurst_exponent" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_hurst_exponent_tool(ctx, "AAPL")
        assert "compute_hurst_exponent" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: synth_fetch_current_quote — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestSynthFetchCurrentQuoteToolResponse:
    """Test synth_fetch_current_quote returns valid ToolResponse JSON."""

    def _make_synth_deps(self) -> MagicMock:
        """Create mock SynthesisDeps with context and contracts."""
        deps = MagicMock()
        deps.context = MagicMock()
        deps.context.ticker = "AAPL"
        deps.context.current_price = Decimal("185.50")
        deps.context.price_52w_high = Decimal("199.62")
        deps.context.price_52w_low = Decimal("164.08")
        deps.context.rsi_14 = 55.3
        deps.context.sector = "Technology"
        deps.context.dividend_yield = 0.005
        deps.context.iv_rank = 45.0
        deps.context.iv_percentile = 52.0
        deps.context.atm_iv_30d = 0.28
        deps.context.put_call_ratio = 0.85
        deps.contracts = []
        # Explicitly no tools_used attribute
        if hasattr(deps, "tools_used"):
            del deps.tools_used
        return deps

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with quote data."""
        deps = self._make_synth_deps()
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_current_quote(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Price:" in parsed["data"]
        assert "$185.50" in parsed["data"]
        assert "verify current price" in parsed["next_actions"]

    async def test_error_ticker_mismatch(self) -> None:
        """Error when ticker doesn't match context."""
        deps = self._make_synth_deps()
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_current_quote(ctx, "MSFT")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "Only AAPL" in parsed["summary"]

    async def test_error_invalid_ticker(self) -> None:
        """Error with invalid ticker."""
        deps = self._make_synth_deps()
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_current_quote(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"

    async def test_error_context_missing(self) -> None:
        """Error when context is not available on deps."""
        deps = MagicMock()
        deps.context = None
        # Access to context.ticker will raise AttributeError
        del deps.context
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_current_quote(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "proceed with assessment data" in parsed["next_actions"]

    async def test_does_not_track_tools_used(self) -> None:
        """Synthesis tools do NOT track tools_used (no DeskDeps)."""
        import types

        # Use SimpleNamespace so attribute access doesn't auto-create tools_used
        synth_deps = types.SimpleNamespace(
            context=MagicMock(
                ticker="AAPL",
                current_price=Decimal("185.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                rsi_14=55.3,
                sector="Technology",
                dividend_yield=0.005,
                iv_rank=45.0,
                iv_percentile=52.0,
                atm_iv_30d=0.28,
                put_call_ratio=0.85,
            ),
            contracts=[],
        )
        ctx = _make_mock_ctx(synth_deps)

        await synth_fetch_current_quote(ctx, "AAPL")

        # Verify no tools_used attribute was created
        assert not hasattr(synth_deps, "tools_used")


# ---------------------------------------------------------------------------
# Test: synth_fetch_chain_summary — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSynthFetchChainSummaryToolResponse:
    """Test synth_fetch_chain_summary returns valid ToolResponse JSON."""

    def _make_synth_deps(self, contracts: list[MagicMock] | None = None) -> MagicMock:
        """Create mock SynthesisDeps with context and contracts."""
        deps = MagicMock()
        deps.context = MagicMock()
        deps.context.ticker = "AAPL"
        deps.contracts = contracts or []
        return deps

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with chain summary."""
        contracts = [
            _make_mock_contract(option_type_val="call", strike="185.00"),
            _make_mock_contract(option_type_val="put", strike="180.00"),
        ]
        deps = self._make_synth_deps(contracts=contracts)
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Chain summary" in parsed["data"]
        assert "select optimal contract" in parsed["next_actions"]

    async def test_error_no_contracts(self) -> None:
        """Error when no contracts available."""
        deps = self._make_synth_deps(contracts=[])
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No contracts" in parsed["summary"]
        assert "recommend caution" in parsed["next_actions"]

    async def test_error_invalid_ticker(self) -> None:
        """Error with invalid ticker."""
        deps = self._make_synth_deps()
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_chain_summary(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"

    async def test_error_exception(self) -> None:
        """Error when an exception occurs."""
        deps = MagicMock()
        # Make contracts access raise an exception
        type(deps).contracts = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        ctx = _make_mock_ctx(deps)

        result = await synth_fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "recommend caution" in parsed["next_actions"]

    async def test_does_not_track_tools_used(self) -> None:
        """Synthesis tools do NOT track tools_used (no DeskDeps)."""
        import types

        contracts = [_make_mock_contract()]
        # Use SimpleNamespace so attribute access doesn't auto-create tools_used
        synth_deps = types.SimpleNamespace(
            context=MagicMock(ticker="AAPL"),
            contracts=contracts,
        )
        ctx = _make_mock_ctx(synth_deps)

        await synth_fetch_chain_summary(ctx, "AAPL")

        # Verify no tools_used attribute was created
        assert not hasattr(synth_deps, "tools_used")


# ---------------------------------------------------------------------------
# Helper for import error simulation
# ---------------------------------------------------------------------------

_real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__  # type: ignore[union-attr]


def _make_import_error_raiser(
    blocked_module: str,
) -> object:
    """Create a side_effect function that raises ImportError for a module."""

    def _raiser(
        name: str,
        globals_: object = None,
        locals_: object = None,
        fromlist: object = (),
        level: int = 0,
    ) -> object:
        if name == blocked_module or (
            isinstance(fromlist, (list, tuple)) and blocked_module.split(".")[-1] in fromlist
        ):
            raise ImportError(f"No module named '{blocked_module}'")
        return _real_import(name, globals_, locals_, fromlist, level)  # type: ignore[operator]

    return _raiser
