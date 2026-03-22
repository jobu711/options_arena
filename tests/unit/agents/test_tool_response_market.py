"""Tests for market data tools refactored to ToolResponse JSON output.

Validates that the 5 market data tools (fetch_quote, fetch_vol_surface_slice,
compute_iv_for_strike, fetch_correlation, fetch_related_ohlcv) return valid
ToolResponse JSON on all code paths.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_iv_for_strike,
    fetch_correlation,
    fetch_quote,
    fetch_related_ohlcv,
    fetch_vol_surface_slice,
)

# ---------------------------------------------------------------------------
# Helpers (reused patterns from test_toolsets.py)
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


def _make_mock_quote(
    ticker: str = "AAPL",
    price: str = "185.50",
    bid: str = "185.48",
    ask: str = "185.52",
    volume: int = 42_000_000,
) -> MagicMock:
    """Create a mock Quote object."""
    quote = MagicMock()
    quote.ticker = ticker
    quote.price = Decimal(price)
    quote.bid = Decimal(bid)
    quote.ask = Decimal(ask)
    quote.volume = volume
    return quote


def _make_mock_ticker_info(
    ticker: str = "AAPL",
    fifty_two_week_high: str = "199.62",
    fifty_two_week_low: str = "164.08",
) -> MagicMock:
    """Create a mock TickerInfo object."""
    info = MagicMock()
    info.ticker = ticker
    info.fifty_two_week_high = Decimal(fifty_two_week_high)
    info.fifty_two_week_low = Decimal(fifty_two_week_low)
    return info


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
    contract.volume = volume
    contract.open_interest = open_interest
    contract.market_iv = market_iv
    return contract


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


def _assert_tool_response_structure(parsed: dict[str, object]) -> None:
    """Assert that a parsed JSON dict has the required ToolResponse fields."""
    assert "status" in parsed
    assert parsed["status"] in {"success", "warning", "error"}
    assert "summary" in parsed
    assert isinstance(parsed["summary"], str)
    assert "next_actions" in parsed
    assert isinstance(parsed["next_actions"], list)


# ---------------------------------------------------------------------------
# Test: fetch_quote — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestFetchQuoteToolResponse:
    """Test fetch_quote returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with status=success."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(return_value=_make_mock_quote())
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Price:" in parsed["data"]
        assert "$185.50" in parsed["data"]
        assert "52W High:" in parsed["data"]
        assert "AAPL" in parsed["summary"]
        assert len(parsed["next_actions"]) > 0

    async def test_error_returns_tool_response_json(self) -> None:
        """Error path returns ToolResponse JSON with status=error."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(side_effect=RuntimeError("connection failed"))

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "AAPL" in parsed["summary"]

    async def test_warning_when_52w_range_fails(self) -> None:
        """Warning status when quote succeeds but 52W range fails."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(return_value=_make_mock_quote())
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("no info"))

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "Price:" in parsed["data"]
        assert "52W High:" not in parsed["data"]
        assert "assess price action without range context" in parsed["next_actions"]

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker format returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_quote(ctx, "!!!invalid!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_quote" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        deps_s.market_data.fetch_quote = AsyncMock(return_value=_make_mock_quote())
        deps_s.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        await fetch_quote(ctx_s, "AAPL")
        assert "fetch_quote" in deps_s.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.market_data.fetch_quote = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_quote(ctx_e, "AAPL")
        assert "fetch_quote" in deps_e.tools_used

        # Invalid ticker
        deps_v = _make_deps()
        ctx_v = _make_mock_ctx(deps_v)
        await fetch_quote(ctx_v, "!!!bad!!!")
        assert "fetch_quote" in deps_v.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_vol_surface_slice — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchVolSurfaceSliceToolResponse:
    """Test fetch_vol_surface_slice returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with IV data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        contracts = [
            _make_mock_contract(strike=f"{170 + i * 5}.00", market_iv=0.20 + i * 0.02)
            for i in range(8)
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Vol surface slice" in parsed["data"]
        assert "IV=" in parsed["data"]
        assert "fetch_vol_surface_slice" in deps.tools_used

    async def test_warning_with_few_contracts(self) -> None:
        """Warning status when fewer than 5 contracts returned."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        contracts = [
            _make_mock_contract(strike="190.00", market_iv=0.28),
            _make_mock_contract(strike="195.00", market_iv=0.30),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "limited contract data" in parsed["next_actions"][1]

    async def test_error_no_expirations(self) -> None:
        """Error status when no expirations found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(return_value=[])

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No option expirations" in parsed["summary"]

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_vol_surface_slice" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_vol_surface_slice(ctx, "AAPL")
        assert "fetch_vol_surface_slice" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_iv_for_strike — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeIVForStrikeToolResponse:
    """Test compute_iv_for_strike returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path finds closest strike and returns ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)
        contracts = [
            _make_mock_contract(strike="180.00", market_iv=0.25),
            _make_mock_contract(strike="190.00", market_iv=0.30),
            _make_mock_contract(strike="200.00", market_iv=0.35),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await compute_iv_for_strike(ctx, "AAPL", 191.0, future_exp.isoformat())
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "190" in parsed["data"]
        assert "IV:" in parsed["data"]
        assert "compare market IV to model IV" in parsed["next_actions"]

    async def test_error_no_contracts(self) -> None:
        """Error status when chain is empty."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)
        deps.options_data.fetch_chain = AsyncMock(return_value=[])

        result = await compute_iv_for_strike(ctx, "AAPL", 190.0, future_exp.isoformat())
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No contracts found" in parsed["summary"]
        assert "compute_iv_for_strike" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)
        deps.options_data.fetch_chain = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_iv_for_strike(ctx, "AAPL", 190.0, future_exp.isoformat())
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_iv_for_strike" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        await compute_iv_for_strike(ctx, "!!!bad!!!", 190.0, "2026-01-01")
        assert "compute_iv_for_strike" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_correlation — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchCorrelationToolResponse:
    """Test fetch_correlation returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with correlations."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        # Create 250+ bars for each ticker to exceed the 20-bar minimum overlap
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

        result = await fetch_correlation(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Correlations with AAPL" in parsed["data"]
        assert "MSFT" in parsed["data"]
        assert "assess diversification benefit" in parsed["next_actions"]

    async def test_warning_partial_data(self) -> None:
        """Warning status when some tickers have insufficient data."""
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
            # GOOG fails
            raise RuntimeError("no data")

        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=_mock_fetch_ohlcv)

        result = await fetch_correlation(ctx, "AAPL", ["MSFT", "GOOG"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert "note incomplete correlation data" in parsed["next_actions"]

    async def test_error_base_ticker_fails(self) -> None:
        """Error status when the base ticker fails to fetch."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network error"))

        result = await fetch_correlation(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_correlation" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status on outer exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        # Make fetch_ohlcv raise immediately (before asyncio.gather)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("boom"))

        result = await fetch_correlation(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_correlation(ctx, "!!!bad!!!", ["MSFT"])
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_correlation" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_correlation(ctx, "AAPL", ["MSFT"])
        assert "fetch_correlation" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_related_ohlcv — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchRelatedOHLCVToolResponse:
    """Test fetch_related_ohlcv returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with OHLCV bars."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(bar_date=date.today() - timedelta(days=5 - i)) for i in range(5)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        result = await fetch_related_ohlcv(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Recent OHLCV for AAPL" in parsed["data"]
        assert "assess recent price action" in parsed["next_actions"]
        assert "fetch_related_ohlcv" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_related_ohlcv(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "AAPL" in parsed["summary"]
        assert "fetch_related_ohlcv" in deps.tools_used

    async def test_error_no_data(self) -> None:
        """Error status when OHLCV data is empty."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await fetch_related_ohlcv(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No OHLCV data" in parsed["summary"]

    async def test_error_invalid_period(self) -> None:
        """Error status with unsupported period."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_related_ohlcv(ctx, "AAPL", period="10y")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "Unsupported period" in parsed["summary"]
        assert "fetch_related_ohlcv" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_related_ohlcv(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_related_ohlcv" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        bars = [_make_mock_ohlcv_bar()]
        deps_s.market_data.fetch_ohlcv = AsyncMock(return_value=bars)
        await fetch_related_ohlcv(ctx_s, "AAPL")
        assert "fetch_related_ohlcv" in deps_s.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_related_ohlcv(ctx_e, "AAPL")
        assert "fetch_related_ohlcv" in deps_e.tools_used

        # Invalid ticker
        deps_v = _make_deps()
        ctx_v = _make_mock_ctx(deps_v)
        await fetch_related_ohlcv(ctx_v, "!!!bad!!!")
        assert "fetch_related_ohlcv" in deps_v.tools_used
