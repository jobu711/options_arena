"""Tests for options/flow and fundamental tools refactored to ToolResponse JSON output.

Validates that the 8 tools (fetch_chain_summary, fetch_unusual_activity,
fetch_portfolio_exposure, compute_indicator_on_demand, fetch_earnings_history,
fetch_sector_comparison, fetch_debate_history, compute_composite_valuation_tool)
return valid ToolResponse JSON on all code paths.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import (
    compute_composite_valuation_tool,
    compute_indicator_on_demand,
    fetch_chain_summary,
    fetch_debate_history,
    fetch_earnings_history,
    fetch_portfolio_exposure,
    fetch_sector_comparison,
    fetch_unusual_activity,
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


def _make_mock_ticker_info(
    ticker: str = "AAPL",
    company_name: str = "Apple Inc.",
    sector: str = "Technology",
    industry: str = "Consumer Electronics",
    market_cap: int = 3_000_000_000_000,
    market_cap_tier: str = "mega_cap",
    dividend_yield: float = 0.005,
    current_price: str = "185.50",
    fifty_two_week_high: str = "199.62",
    fifty_two_week_low: str = "164.08",
    short_ratio: float | None = 1.5,
    short_pct_of_float: float | None = 0.008,
) -> MagicMock:
    """Create a mock TickerInfo object."""
    info = MagicMock()
    info.ticker = ticker
    info.company_name = company_name
    info.sector = sector
    info.industry = industry
    info.market_cap = market_cap
    info.market_cap_tier = MagicMock()
    info.market_cap_tier.value = market_cap_tier
    info.dividend_yield = dividend_yield
    info.current_price = Decimal(current_price)
    info.fifty_two_week_high = Decimal(fifty_two_week_high)
    info.fifty_two_week_low = Decimal(fifty_two_week_low)
    info.short_ratio = short_ratio
    info.short_pct_of_float = short_pct_of_float
    return info


def _make_mock_debate(
    debate_id: int = 1,
    ticker: str = "AAPL",
    is_fallback: bool = False,
    verdict_json: str | None = None,
) -> MagicMock:
    """Create a mock debate record."""
    debate = MagicMock()
    debate.id = debate_id
    debate.ticker = ticker
    debate.is_fallback = is_fallback
    debate.created_at = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    debate.verdict_json = verdict_json
    return debate


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


def _make_mock_valuation_result(
    ticker: str = "AAPL",
    current_price: float = 185.50,
    composite_fair_value: float | None = 200.0,
    composite_margin_of_safety: float | None = 0.078,
    valuation_signal_val: str | None = "undervalued",
    model_results: list[MagicMock] | None = None,
) -> MagicMock:
    """Create a mock CompositeValuation result."""
    result = MagicMock()
    result.ticker = ticker
    result.current_price = current_price
    result.composite_fair_value = composite_fair_value
    result.composite_margin_of_safety = composite_margin_of_safety
    if valuation_signal_val is not None:
        result.valuation_signal = MagicMock()
        result.valuation_signal.value = valuation_signal_val
    else:
        result.valuation_signal = None
    if model_results is not None:
        result.models = model_results
    else:
        m1 = MagicMock()
        m1.fair_value = 200.0
        m1.margin_of_safety = 0.078
        m1.methodology = "Owner Earnings DCF"
        m1.confidence = 0.7
        result.models = [m1]
    return result


def _assert_tool_response_structure(parsed: dict[str, object]) -> None:
    """Assert that a parsed JSON dict has the required ToolResponse fields."""
    assert "status" in parsed
    assert parsed["status"] in {"success", "warning", "error"}
    assert "summary" in parsed
    assert isinstance(parsed["summary"], str)
    assert "next_actions" in parsed
    assert isinstance(parsed["next_actions"], list)


# ---------------------------------------------------------------------------
# Test: fetch_chain_summary — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestFetchChainSummaryToolResponse:
    """Test fetch_chain_summary returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with chain data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        contracts = [
            _make_mock_contract(option_type_val="call", volume=500, open_interest=5000),
            _make_mock_contract(option_type_val="put", volume=300, open_interest=3000),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Chain summary" in parsed["data"]
        assert "Calls:" in parsed["data"]
        assert "Puts:" in parsed["data"]
        assert "assess put/call ratio" in parsed["next_actions"]
        assert "fetch_chain_summary" in deps.tools_used

    async def test_warning_when_one_side_missing_oi(self) -> None:
        """Warning status when one side has zero OI."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        contracts = [
            _make_mock_contract(option_type_val="call", volume=500, open_interest=0),
            _make_mock_contract(option_type_val="put", volume=300, open_interest=3000),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None

    async def test_error_no_expirations(self) -> None:
        """Error status when no expirations found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(return_value=[])

        result = await fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No option expirations" in parsed["summary"]
        assert "fetch_chain_summary" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_chain_summary(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_chain_summary" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker format returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_chain_summary(ctx, "!!!invalid!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_chain_summary" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        future_exp = date.today() + timedelta(days=30)
        deps_s.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        deps_s.options_data.fetch_chain = AsyncMock(
            return_value=[_make_mock_contract(option_type_val="call")]
        )
        await fetch_chain_summary(ctx_s, "AAPL")
        assert "fetch_chain_summary" in deps_s.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_chain_summary(ctx_e, "AAPL")
        assert "fetch_chain_summary" in deps_e.tools_used

        # Invalid ticker
        deps_v = _make_deps()
        ctx_v = _make_mock_ctx(deps_v)
        await fetch_chain_summary(ctx_v, "!!!bad!!!")
        assert "fetch_chain_summary" in deps_v.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_unusual_activity — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchUnusualActivityToolResponse:
    """Test fetch_unusual_activity returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with unusual contracts."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        # Volume > 3x OI = unusual
        contracts = [
            _make_mock_contract(volume=5000, open_interest=1000),
            _make_mock_contract(volume=100, open_interest=5000),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_unusual_activity(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Unusual activity" in parsed["data"]
        assert "assess direction of unusual flow" in parsed["next_actions"]
        assert "fetch_unusual_activity" in deps.tools_used

    async def test_warning_no_unusual_activity(self) -> None:
        """Warning status when chain fetched but no unusual contracts found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        future_exp = date.today() + timedelta(days=30)

        deps.options_data.fetch_expirations = AsyncMock(return_value=[future_exp])
        # Volume < 3x OI = normal
        contracts = [
            _make_mock_contract(volume=100, open_interest=5000),
            _make_mock_contract(volume=200, open_interest=8000),
        ]
        deps.options_data.fetch_chain = AsyncMock(return_value=contracts)

        result = await fetch_unusual_activity(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "note absence of unusual activity" in parsed["next_actions"]
        assert "fetch_unusual_activity" in deps.tools_used

    async def test_error_no_expirations(self) -> None:
        """Error status when no expirations found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(return_value=[])

        result = await fetch_unusual_activity(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No option expirations" in parsed["summary"]

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_unusual_activity(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_unusual_activity" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_unusual_activity(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_unusual_activity" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.options_data.fetch_expirations = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_unusual_activity(ctx, "AAPL")
        assert "fetch_unusual_activity" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_portfolio_exposure — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchPortfolioExposureToolResponse:
    """Test fetch_portfolio_exposure returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with prior recommendations."""
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
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Recent recommended contracts" in parsed["data"]
        assert "CALL" in parsed["data"]
        assert "assess existing exposure overlap" in parsed["next_actions"]
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_warning_no_prior_recommendations(self) -> None:
        """Warning status when no prior recommendations found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_contracts_for_ticker = AsyncMock(return_value=[])

        result = await fetch_portfolio_exposure(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "no prior positions to assess" in parsed["next_actions"]
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_error_repo_exception(self) -> None:
        """Error status when repository query fails."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_contracts_for_ticker = AsyncMock(side_effect=RuntimeError("db error"))

        result = await fetch_portfolio_exposure(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_portfolio_exposure(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_portfolio_exposure" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, warning, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        deps_s.repo.get_contracts_for_ticker = AsyncMock(
            return_value=[_make_mock_recommended_contract()]
        )
        await fetch_portfolio_exposure(ctx_s, "AAPL")
        assert "fetch_portfolio_exposure" in deps_s.tools_used

        # Warning (empty)
        deps_w = _make_deps()
        ctx_w = _make_mock_ctx(deps_w)
        deps_w.repo.get_contracts_for_ticker = AsyncMock(return_value=[])
        await fetch_portfolio_exposure(ctx_w, "AAPL")
        assert "fetch_portfolio_exposure" in deps_w.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.repo.get_contracts_for_ticker = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_portfolio_exposure(ctx_e, "AAPL")
        assert "fetch_portfolio_exposure" in deps_e.tools_used


# ---------------------------------------------------------------------------
# Test: compute_indicator_on_demand — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeIndicatorOnDemandToolResponse:
    """Test compute_indicator_on_demand returns valid ToolResponse JSON."""

    async def test_success_rsi_returns_tool_response_json(self) -> None:
        """Success path for RSI returns ToolResponse JSON."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        bars = [
            _make_mock_ohlcv_bar(
                bar_date=date.today() - timedelta(days=252 - i),
                close=str(Decimal("150.00") + Decimal(str(i)) * Decimal("0.10")),
                high=str(Decimal("151.00") + Decimal(str(i)) * Decimal("0.10")),
                low=str(Decimal("149.00") + Decimal(str(i)) * Decimal("0.10")),
            )
            for i in range(252)
        ]
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=bars)

        result = await compute_indicator_on_demand(ctx, "AAPL", "rsi")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] in {"success", "warning"}
        assert parsed["data"] is not None
        assert "RSI" in parsed["data"]
        assert "compute_indicator_on_demand" in deps.tools_used

    async def test_error_unsupported_indicator(self) -> None:
        """Error status for unsupported indicator name."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_indicator_on_demand(ctx, "AAPL", "bollinger")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "Unsupported indicator" in parsed["summary"]
        assert "compute_indicator_on_demand" in deps.tools_used

    async def test_error_no_ohlcv_data(self) -> None:
        """Error status when no OHLCV data found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(return_value=[])

        result = await compute_indicator_on_demand(ctx, "AAPL", "rsi")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "No OHLCV data" in parsed["summary"]

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_indicator_on_demand(ctx, "AAPL", "rsi")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "compute_indicator_on_demand" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_indicator_on_demand(ctx, "!!!bad!!!", "rsi")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_indicator_on_demand" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ohlcv = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_indicator_on_demand(ctx, "AAPL", "rsi")
        assert "compute_indicator_on_demand" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_earnings_history — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchEarningsHistoryToolResponse:
    """Test fetch_earnings_history returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with fundamental data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.market_data.fetch_earnings_date = AsyncMock(
            return_value=date.today() + timedelta(days=14)
        )

        result = await fetch_earnings_history(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Fundamentals for AAPL" in parsed["data"]
        assert "Sector:" in parsed["data"]
        assert "Dividend Yield:" in parsed["data"]
        assert "note upcoming earnings risk" in parsed["next_actions"]
        assert "fetch_earnings_history" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_earnings_history(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_earnings_history" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_earnings_history(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_earnings_history" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        deps_s.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps_s.market_data.fetch_earnings_date = AsyncMock(return_value=None)
        await fetch_earnings_history(ctx_s, "AAPL")
        assert "fetch_earnings_history" in deps_s.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_earnings_history(ctx_e, "AAPL")
        assert "fetch_earnings_history" in deps_e.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_sector_comparison — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchSectorComparisonToolResponse:
    """Test fetch_sector_comparison returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with sector data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())

        result = await fetch_sector_comparison(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Sector comparison" in parsed["data"]
        assert "Technology" in parsed["data"]
        assert "compare vs sector peers" in parsed["next_actions"]
        assert "fetch_sector_comparison" in deps.tools_used

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))

        result = await fetch_sector_comparison(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_sector_comparison" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_sector_comparison(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_sector_comparison" in deps.tools_used

    async def test_tools_used_tracked(self) -> None:
        """tools_used is updated on all paths."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_sector_comparison(ctx, "AAPL")
        assert "fetch_sector_comparison" in deps.tools_used


# ---------------------------------------------------------------------------
# Test: fetch_debate_history — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFetchDebateHistoryToolResponse:
    """Test fetch_debate_history returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with debate data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        verdict = (
            '{"ticker":"AAPL","direction":"bullish","confidence":0.75,'
            '"summary":"Strong technical setup","bull_score":0.8,"bear_score":0.3,'
            '"key_factors":["RSI"],"risk_assessment":"moderate"}'
        )
        debates = [_make_mock_debate(verdict_json=verdict)]
        deps.repo.get_debates_for_ticker = AsyncMock(return_value=debates)

        result = await fetch_debate_history(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Recent debate history" in parsed["data"]
        assert "note prior consensus direction" in parsed["next_actions"]
        assert "fetch_debate_history" in deps.tools_used

    async def test_warning_no_prior_debates(self) -> None:
        """Warning status when no prior debates found."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_debates_for_ticker = AsyncMock(return_value=[])

        result = await fetch_debate_history(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "no prior analysis to reference" in parsed["next_actions"]
        assert "fetch_debate_history" in deps.tools_used

    async def test_error_repo_exception(self) -> None:
        """Error status when repository query fails."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.repo.get_debates_for_ticker = AsyncMock(side_effect=RuntimeError("db error"))

        result = await fetch_debate_history(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "fetch_debate_history" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await fetch_debate_history(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "fetch_debate_history" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, warning, error, and invalid ticker."""
        # Success
        deps_s = _make_deps()
        ctx_s = _make_mock_ctx(deps_s)
        verdict = (
            '{"ticker":"AAPL","direction":"bullish","confidence":0.7,'
            '"summary":"Test","bull_score":0.8,"bear_score":0.3,'
            '"key_factors":["x"],"risk_assessment":"low"}'
        )
        deps_s.repo.get_debates_for_ticker = AsyncMock(
            return_value=[_make_mock_debate(verdict_json=verdict)]
        )
        await fetch_debate_history(ctx_s, "AAPL")
        assert "fetch_debate_history" in deps_s.tools_used

        # Warning (empty)
        deps_w = _make_deps()
        ctx_w = _make_mock_ctx(deps_w)
        deps_w.repo.get_debates_for_ticker = AsyncMock(return_value=[])
        await fetch_debate_history(ctx_w, "AAPL")
        assert "fetch_debate_history" in deps_w.tools_used

        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.repo.get_debates_for_ticker = AsyncMock(side_effect=RuntimeError("fail"))
        await fetch_debate_history(ctx_e, "AAPL")
        assert "fetch_debate_history" in deps_e.tools_used


# ---------------------------------------------------------------------------
# Test: compute_composite_valuation_tool — ToolResponse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestComputeCompositeValuationToolResponse:
    """Test compute_composite_valuation_tool returns valid ToolResponse JSON."""

    async def test_success_returns_tool_response_json(self) -> None:
        """Success path returns ToolResponse JSON with valuation data."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_result = _make_mock_valuation_result()

        with patch(
            "options_arena.analysis.valuation.compute_composite_valuation",
            return_value=mock_result,
        ):
            result = await compute_composite_valuation_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "success"
        assert parsed["data"] is not None
        assert "Composite Valuation" in parsed["data"]
        assert "compare fair value to current price" in parsed["next_actions"]
        assert "compute_composite_valuation" in deps.tools_used

    async def test_warning_no_models_produced_fair_value(self) -> None:
        """Warning status when no valuation models produced fair value."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        # All models have fair_value=None
        m1 = MagicMock()
        m1.fair_value = None
        m1.margin_of_safety = None
        m1.methodology = "Owner Earnings DCF"
        m1.confidence = 0.3
        mock_result = _make_mock_valuation_result(
            composite_fair_value=None,
            composite_margin_of_safety=None,
            valuation_signal_val=None,
            model_results=[m1],
        )

        with patch(
            "options_arena.analysis.valuation.compute_composite_valuation",
            return_value=mock_result,
        ):
            result = await compute_composite_valuation_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert parsed["data"] is not None
        assert "assess available methods only" in parsed["next_actions"]
        assert "compute_composite_valuation" in deps.tools_used

    async def test_warning_partial_models(self) -> None:
        """Warning status when some but not all models computed fair value."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(return_value=_make_mock_ticker_info())
        deps.fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        m1 = MagicMock()
        m1.fair_value = 200.0
        m1.margin_of_safety = 0.08
        m1.methodology = "Owner Earnings DCF"
        m1.confidence = 0.7
        m2 = MagicMock()
        m2.fair_value = None
        m2.margin_of_safety = None
        m2.methodology = "DDM"
        m2.confidence = 0.0
        mock_result = _make_mock_valuation_result(model_results=[m1, m2])

        with patch(
            "options_arena.analysis.valuation.compute_composite_valuation",
            return_value=mock_result,
        ):
            result = await compute_composite_valuation_tool(ctx, "AAPL")
            parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "warning"
        assert "1/2" in parsed["summary"]

    async def test_error_service_exception(self) -> None:
        """Error status when service raises an exception."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)
        deps.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))

        result = await compute_composite_valuation_tool(ctx, "AAPL")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert parsed["data"] is None
        assert "compute_composite_valuation" in deps.tools_used

    async def test_invalid_ticker_returns_error(self) -> None:
        """Invalid ticker returns ToolResponse JSON with error status."""
        deps = _make_deps()
        ctx = _make_mock_ctx(deps)

        result = await compute_composite_valuation_tool(ctx, "!!!bad!!!")
        parsed = json.loads(result)

        _assert_tool_response_structure(parsed)
        assert parsed["status"] == "error"
        assert "compute_composite_valuation" in deps.tools_used

    async def test_tools_used_tracked_on_all_paths(self) -> None:
        """tools_used is updated on success, error, and invalid ticker."""
        # Error
        deps_e = _make_deps()
        ctx_e = _make_mock_ctx(deps_e)
        deps_e.market_data.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("fail"))
        await compute_composite_valuation_tool(ctx_e, "AAPL")
        assert "compute_composite_valuation" in deps_e.tools_used

        # Invalid ticker
        deps_v = _make_deps()
        ctx_v = _make_mock_ctx(deps_v)
        await compute_composite_valuation_tool(ctx_v, "!!!bad!!!")
        assert "compute_composite_valuation" in deps_v.tools_used
