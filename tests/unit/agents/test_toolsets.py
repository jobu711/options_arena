"""Tests for tool wrappers and toolset builders."""

from __future__ import annotations

import inspect
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    build_risk_toolset,
    build_volatility_toolset,
    compute_iv_for_strike,
    fetch_correlation,
    fetch_portfolio_exposure,
    fetch_quote,
    fetch_vol_surface_slice,
)

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


def _make_mock_recommended_contract(
    ticker: str = "AAPL",
    option_type_val: str = "call",
    strike: str = "190.00",
    expiration: date | None = None,
    direction_val: str = "bullish",
    composite_score: float = 72.5,
    entry_mid: str = "4.65",
) -> MagicMock:
    """Create a mock RecommendedContract object."""
    contract = MagicMock()
    contract.ticker = ticker
    contract.option_type = MagicMock()
    contract.option_type.value = option_type_val
    contract.strike = Decimal(strike)
    contract.expiration = expiration or (date.today() + timedelta(days=45))
    contract.direction = MagicMock()
    contract.direction.value = direction_val
    contract.composite_score = composite_score
    contract.entry_mid = Decimal(entry_mid)
    return contract


# ---------------------------------------------------------------------------
# Test: build_volatility_toolset / build_risk_toolset
# ---------------------------------------------------------------------------


@pytest.mark.critical
class TestBuildToolsets:
    """Test toolset builder functions."""

    def test_volatility_toolset_has_four_tools(self) -> None:
        """Volatility toolset contains exactly 4 tools."""
        tools = build_volatility_toolset()
        assert len(tools) == 4

    def test_risk_toolset_has_expected_tools(self) -> None:
        """Risk toolset contains 7-8 tools (8 with [ml])."""
        tools = build_risk_toolset()
        assert len(tools) in {7, 8}

    def test_volatility_toolset_contains_expected_functions(self) -> None:
        """Volatility toolset contains the expected tool functions."""
        tools = build_volatility_toolset()
        assert fetch_quote in tools
        assert fetch_vol_surface_slice in tools
        assert compute_iv_for_strike in tools

    def test_risk_toolset_contains_expected_functions(self) -> None:
        """Risk toolset contains fetch_quote, fetch_correlation, fetch_portfolio_exposure."""
        tools = build_risk_toolset()
        assert fetch_quote in tools
        assert fetch_correlation in tools
        assert fetch_portfolio_exposure in tools

    def test_fetch_quote_shared_between_toolsets(self) -> None:
        """fetch_quote appears in both volatility and risk toolsets."""
        vol_tools = build_volatility_toolset()
        risk_tools = build_risk_toolset()
        assert fetch_quote in vol_tools
        assert fetch_quote in risk_tools


# ---------------------------------------------------------------------------
# Test: fetch_quote tool
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestFetchQuoteTool:
    """Test the fetch_quote tool wrapper."""

    async def test_success_returns_formatted_string(self) -> None:
        """Successful fetch returns ToolResponse JSON with Price: in data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        mock_quote = _make_mock_quote()
        mock_info = _make_mock_ticker_info()

        deps.market_data.fetch_quote = AsyncMock(return_value=mock_quote)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=mock_info)

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] == "success"
        assert "Price:" in parsed["data"]
        assert "$185.50" in parsed["data"]
        assert "Volume:" in parsed["data"]
        assert "52W High:" in parsed["data"]

    async def test_failure_returns_error_string(self) -> None:
        """Service error returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(side_effect=RuntimeError("connection failed"))

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] == "error"
        assert "AAPL" in parsed["summary"]

    async def test_appends_to_tools_used_on_success(self) -> None:
        """Tool name appended to tools_used on success."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(return_value=_make_mock_quote())
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())

        await fetch_quote(ctx, "AAPL")

        assert "fetch_quote" in deps.tools_used

    async def test_appends_to_tools_used_on_error(self) -> None:
        """Tool name appended to tools_used on error."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(side_effect=RuntimeError("fail"))

        await fetch_quote(ctx, "AAPL")

        assert "fetch_quote" in deps.tools_used

    async def test_52w_range_optional(self) -> None:
        """If ticker_info fails, quote returns warning status without 52W data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_quote = AsyncMock(return_value=_make_mock_quote())
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("no info"))

        result = await fetch_quote(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] == "warning"
        assert "Price:" in parsed["data"]
        assert "52W High:" not in parsed["data"]


# ---------------------------------------------------------------------------
# Test: fetch_vol_surface_slice tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchVolSurfaceSliceTool:
    """Test the fetch_vol_surface_slice tool wrapper."""

    async def test_success_returns_iv_data(self) -> None:
        """Successful fetch returns ToolResponse JSON with IV data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        contracts = [
            _make_mock_contract(strike="180.00", market_iv=0.25),
            _make_mock_contract(strike="190.00", market_iv=0.28),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] in {"success", "warning"}
        assert "Vol surface slice" in parsed["data"]
        assert "IV=" in parsed["data"]
        assert "fetch_vol_surface_slice" in deps.tools_used

    async def test_no_expirations_returns_message(self) -> None:
        """No expirations returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(return_value=[])

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] == "error"
        assert "No option expirations" in parsed["summary"]
        assert "fetch_vol_surface_slice" in deps.tools_used

    async def test_error_returns_error_string(self) -> None:
        """Service error returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_vol_surface_slice(ctx, "AAPL")
        parsed = json.loads(result)

        assert parsed["status"] == "error"
        assert "fetch_vol_surface_slice" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: compute_iv_for_strike tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeIVForStrikeTool:
    """Test the compute_iv_for_strike tool wrapper."""

    async def test_finds_closest_strike(self) -> None:
        """Finds the closest strike in the chain."""
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

        assert parsed["status"] == "success"
        assert "190" in parsed["data"]
        assert "IV:" in parsed["data"]
        assert "compute_iv_for_strike" in deps.tools_used

    async def test_no_contracts_returns_message(self) -> None:
        """Empty chain returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)
        deps.options_data.fetch_chain = AsyncMock(return_value=[])

        result = await compute_iv_for_strike(ctx, "AAPL", 190.0, future_exp.isoformat())
        parsed = json.loads(result)

        assert parsed["status"] == "error"
        assert "No contracts found" in parsed["summary"]
        assert "compute_iv_for_strike" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_portfolio_exposure tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchPortfolioExposureTool:
    """Test the fetch_portfolio_exposure tool wrapper."""

    async def test_no_contracts_returns_message(self) -> None:
        """Empty repo returns informative message."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_contracts_for_ticker = AsyncMock(return_value=[])

        result = await fetch_portfolio_exposure(ctx, "AAPL")

        assert "No historical recommended contracts" in result
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_repo_error_returns_error_string(self) -> None:
        """Repository error returns Error: string."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_contracts_for_ticker = AsyncMock(side_effect=RuntimeError("db error"))

        result = await fetch_portfolio_exposure(ctx, "AAPL")

        assert result.startswith("Error:")
        assert "AAPL" in result
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_success_returns_contract_details(self) -> None:
        """Successful query returns formatted contract details."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        mock_contracts = [
            _make_mock_recommended_contract(
                ticker="AAPL",
                option_type_val="call",
                strike="190.00",
                direction_val="bullish",
                composite_score=72.5,
            ),
        ]
        deps.repo.get_contracts_for_ticker = AsyncMock(return_value=mock_contracts)

        result = await fetch_portfolio_exposure(ctx, "AAPL")

        assert "Recent recommended contracts" in result
        assert "CALL" in result
        assert "$190" in result
        assert "fetch_portfolio_exposure" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_correlation tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchCorrelationTool:
    """Test the fetch_correlation tool wrapper."""

    async def test_error_returns_error_string(self) -> None:
        """Service error returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("network error"))

        result = await fetch_correlation(ctx, "AAPL", ["MSFT"])
        parsed = json.loads(result)

        assert parsed["status"] == "error"
        assert "fetch_correlation" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: Tool annotations
# ---------------------------------------------------------------------------


class TestToolAnnotations:
    """Test that all tools have correct signatures and are async."""

    def test_all_tools_are_async(self) -> None:
        """All tool functions must be async (coroutine functions)."""
        tools = [
            fetch_quote,
            fetch_vol_surface_slice,
            compute_iv_for_strike,
            fetch_correlation,
            fetch_portfolio_exposure,
        ]
        for tool in tools:
            assert inspect.iscoroutinefunction(tool), f"{tool.__name__} is not async"

    def test_fetch_quote_signature(self) -> None:
        """fetch_quote accepts RunContext and ticker string."""
        sig = inspect.signature(fetch_quote)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker"]

    def test_compute_iv_for_strike_signature(self) -> None:
        """compute_iv_for_strike accepts RunContext, ticker, strike, expiry."""
        sig = inspect.signature(compute_iv_for_strike)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker", "strike", "expiry"]

    def test_fetch_correlation_signature(self) -> None:
        """fetch_correlation accepts RunContext, ticker, and tickers list."""
        sig = inspect.signature(fetch_correlation)
        params = list(sig.parameters.keys())
        assert params == ["ctx", "ticker", "tickers"]

    def test_all_tools_return_str(self) -> None:
        """All tool functions have str return annotation.

        Because ``from __future__ import annotations`` is active in
        ``_toolsets.py``, annotations are stored as string literals.
        We check the raw ``__annotations__`` dict for ``"str"``.
        """
        tools = [
            fetch_quote,
            fetch_vol_surface_slice,
            compute_iv_for_strike,
            fetch_correlation,
            fetch_portfolio_exposure,
        ]
        for tool in tools:
            ret = tool.__annotations__.get("return")
            assert ret == "str", f"{tool.__name__} return annotation is {ret!r}, expected 'str'"
