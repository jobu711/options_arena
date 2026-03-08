"""Unit tests for FinancialDatasetsService.

Tests cover:
- fetch_financial_metrics: happy path, cache hit/miss, config disabled, no API key, errors
- fetch_income_statement: happy path, cache hit, errors
- fetch_balance_sheet: happy path, cache hit, errors
- fetch_package: parallel gather, partial success, all fail
- close: calls aclose on httpx client
- Rate limiter usage
- Empty response array handling
- Timeout handling
- Never-raises contract on all public methods
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from options_arena.models.config import FinancialDatasetsConfig
from options_arena.models.financial_datasets import (
    BalanceSheetData,
    FinancialDatasetsPackage,
    FinancialMetricsData,
    IncomeStatementData,
)
from options_arena.services.financial_datasets import FinancialDatasetsService

# ---------------------------------------------------------------------------
# Sample API response data
# ---------------------------------------------------------------------------

_SAMPLE_METRICS_RESPONSE: dict[str, object] = {
    "financial_metrics": [
        {
            "pe_ratio": 25.5,
            "forward_pe": 22.0,
            "peg_ratio": 1.5,
            "price_to_book": 8.2,
            "price_to_sales": 6.1,
            "enterprise_value_to_ebitda": 18.3,
            "enterprise_value_to_revenue": 5.9,
            "gross_margin": 0.45,
            "operating_margin": 0.30,
            "net_margin": 0.25,
            "profit_margin": 0.24,
            "revenue_growth": 0.12,
            "earnings_growth": 0.15,
            "return_on_equity": 0.35,
            "return_on_assets": 0.20,
            "return_on_capital": 0.28,
            "debt_to_equity": 0.8,
            "current_ratio": 1.5,
            "eps_diluted": 6.50,
            "free_cash_flow_yield": 0.04,
            "dividend_yield": 0.006,
        }
    ]
}

_SAMPLE_INCOME_RESPONSE: dict[str, object] = {
    "income_statements": [
        {
            "revenue": 394_328_000_000.0,
            "gross_profit": 170_782_000_000.0,
            "operating_income": 114_301_000_000.0,
            "net_income": 96_995_000_000.0,
            "eps_diluted": 6.13,
            "gross_margin": 0.433,
            "operating_margin": 0.290,
            "net_margin": 0.246,
        }
    ]
}

_SAMPLE_BALANCE_RESPONSE: dict[str, object] = {
    "balance_sheets": [
        {
            "total_assets": 352_583_000_000.0,
            "total_liabilities": 290_437_000_000.0,
            "total_equity": 62_146_000_000.0,
            "total_debt": 111_088_000_000.0,
            "total_cash": 29_965_000_000.0,
            "current_assets": 143_566_000_000.0,
            "current_liabilities": 145_308_000_000.0,
            "shares_outstanding": 15_334_000_000,
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> FinancialDatasetsConfig:
    """Enabled config with API key."""
    return FinancialDatasetsConfig(enabled=True, api_key="test-key-123")


@pytest.fixture
def disabled_config() -> FinancialDatasetsConfig:
    """Config with enabled=False."""
    return FinancialDatasetsConfig(enabled=False, api_key="test-key-123")


@pytest.fixture
def no_key_config() -> FinancialDatasetsConfig:
    """Config with no API key."""
    return FinancialDatasetsConfig(enabled=True, api_key=None)


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create a mock ServiceCache."""
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_limiter() -> MagicMock:
    """Create a mock RateLimiter that acts as async context manager."""
    limiter = MagicMock()
    limiter.__aenter__ = AsyncMock(return_value=limiter)
    limiter.__aexit__ = AsyncMock(return_value=None)
    return limiter


def _make_service(
    config: FinancialDatasetsConfig,
    cache: MagicMock,
    limiter: MagicMock,
) -> FinancialDatasetsService:
    """Create FinancialDatasetsService with mocked dependencies."""
    return FinancialDatasetsService(config=config, cache=cache, limiter=limiter)


def _make_httpx_response(body: dict[str, object], status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with JSON body."""
    return httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://api.financialdatasets.ai/api/v1/test"),
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )


# ---------------------------------------------------------------------------
# fetch_financial_metrics tests
# ---------------------------------------------------------------------------


class TestFetchFinancialMetrics:
    """Tests for fetch_financial_metrics method."""

    @pytest.mark.asyncio
    async def test_happy_path(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify metrics fetch with mocked API response."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response(_SAMPLE_METRICS_RESPONSE)

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            result = await service.fetch_financial_metrics("AAPL")

        assert result is not None
        assert isinstance(result, FinancialMetricsData)
        assert result.pe_ratio == pytest.approx(25.5)
        assert result.forward_pe == pytest.approx(22.0)
        assert result.gross_margin == pytest.approx(0.45)
        assert result.dividend_yield == pytest.approx(0.006)
        await service.close()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify cache hit returns cached data without API call."""
        cached_data = FinancialMetricsData(pe_ratio=20.0)
        mock_cache.get = AsyncMock(return_value=cached_data.model_dump_json().encode())
        service = _make_service(config, mock_cache, mock_limiter)

        with patch.object(service._client, "get", new_callable=AsyncMock) as mock_get:
            result = await service.fetch_financial_metrics("AAPL")

        assert result is not None
        assert result.pe_ratio == pytest.approx(20.0)
        mock_get.assert_not_called()
        await service.close()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify successful fetch stores result in cache."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response(_SAMPLE_METRICS_RESPONSE)

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            await service.fetch_financial_metrics("AAPL")

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "fd:metrics:AAPL:ttm"
        assert call_args[1]["ttl"] == config.cache_ttl
        await service.close()

    @pytest.mark.asyncio
    async def test_config_disabled_returns_none(
        self,
        disabled_config: FinancialDatasetsConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Verify service no-ops when config.enabled=False."""
        service = _make_service(disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_financial_metrics("AAPL")
        assert result is None
        await service.close()

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(
        self,
        no_key_config: FinancialDatasetsConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Verify service no-ops when api_key is None."""
        service = _make_service(no_key_config, mock_cache, mock_limiter)
        result = await service.fetch_financial_metrics("AAPL")
        assert result is None
        await service.close()

    @pytest.mark.asyncio
    async def test_api_error_returns_none(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify HTTP errors return None (never-raises)."""
        service = _make_service(config, mock_cache, mock_limiter)
        error_response = _make_httpx_response({"error": "Forbidden"}, status_code=403)

        with patch.object(
            service._client, "get", new_callable=AsyncMock, return_value=error_response
        ):
            result = await service.fetch_financial_metrics("AAPL")

        assert result is None
        await service.close()

    @pytest.mark.asyncio
    async def test_timeout_returns_none(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify timeout returns None (never-raises)."""
        service = _make_service(config, mock_cache, mock_limiter)

        async def _slow_get(*args: object, **kwargs: object) -> httpx.Response:
            raise TimeoutError("timed out")

        with patch.object(service._client, "get", side_effect=_slow_get):
            result = await service.fetch_financial_metrics("AAPL")

        assert result is None
        await service.close()

    @pytest.mark.asyncio
    async def test_empty_response_array(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify empty JSON array returns None gracefully."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response({"financial_metrics": []})

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            result = await service.fetch_financial_metrics("AAPL")

        assert result is None
        await service.close()


# ---------------------------------------------------------------------------
# fetch_income_statement tests
# ---------------------------------------------------------------------------


class TestFetchIncomeStatement:
    """Tests for fetch_income_statement method."""

    @pytest.mark.asyncio
    async def test_happy_path(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify income statement fetch with mocked API response."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response(_SAMPLE_INCOME_RESPONSE)

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            result = await service.fetch_income_statement("AAPL")

        assert result is not None
        assert isinstance(result, IncomeStatementData)
        assert result.revenue == pytest.approx(394_328_000_000.0)
        assert result.net_margin == pytest.approx(0.246)
        await service.close()

    @pytest.mark.asyncio
    async def test_cache_hit(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify cache hit for income statement."""
        cached_data = IncomeStatementData(revenue=100_000_000.0)
        mock_cache.get = AsyncMock(return_value=cached_data.model_dump_json().encode())
        service = _make_service(config, mock_cache, mock_limiter)

        with patch.object(service._client, "get", new_callable=AsyncMock) as mock_get:
            result = await service.fetch_income_statement("AAPL")

        assert result is not None
        assert result.revenue == pytest.approx(100_000_000.0)
        mock_get.assert_not_called()
        await service.close()


# ---------------------------------------------------------------------------
# fetch_balance_sheet tests
# ---------------------------------------------------------------------------


class TestFetchBalanceSheet:
    """Tests for fetch_balance_sheet method."""

    @pytest.mark.asyncio
    async def test_happy_path(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify balance sheet fetch with mocked API response."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response(_SAMPLE_BALANCE_RESPONSE)

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            result = await service.fetch_balance_sheet("AAPL")

        assert result is not None
        assert isinstance(result, BalanceSheetData)
        assert result.total_assets == pytest.approx(352_583_000_000.0)
        assert result.shares_outstanding == 15_334_000_000
        await service.close()

    @pytest.mark.asyncio
    async def test_cache_hit(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify cache hit for balance sheet."""
        cached_data = BalanceSheetData(total_assets=500_000_000.0)
        mock_cache.get = AsyncMock(return_value=cached_data.model_dump_json().encode())
        service = _make_service(config, mock_cache, mock_limiter)

        with patch.object(service._client, "get", new_callable=AsyncMock) as mock_get:
            result = await service.fetch_balance_sheet("AAPL")

        assert result is not None
        assert result.total_assets == pytest.approx(500_000_000.0)
        mock_get.assert_not_called()
        await service.close()


# ---------------------------------------------------------------------------
# fetch_package tests
# ---------------------------------------------------------------------------


class TestFetchPackage:
    """Tests for fetch_package method."""

    @pytest.mark.asyncio
    async def test_fetch_package_parallel(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify fetch_package calls all 3 endpoints via gather."""
        service = _make_service(config, mock_cache, mock_limiter)

        # Return different responses based on URL path
        async def _mock_get(path: str, **kwargs: object) -> httpx.Response:
            if "financial-metrics" in path:
                return _make_httpx_response(_SAMPLE_METRICS_RESPONSE)
            if "income-statements" in path:
                return _make_httpx_response(_SAMPLE_INCOME_RESPONSE)
            if "balance-sheets" in path:
                return _make_httpx_response(_SAMPLE_BALANCE_RESPONSE)
            return _make_httpx_response({}, status_code=404)

        with patch.object(service._client, "get", side_effect=_mock_get):
            result = await service.fetch_package("AAPL")

        assert result is not None
        assert isinstance(result, FinancialDatasetsPackage)
        assert result.ticker == "AAPL"
        assert result.metrics is not None
        assert result.income is not None
        assert result.balance_sheet is not None
        assert result.fetched_at is not None
        await service.close()

    @pytest.mark.asyncio
    async def test_partial_package_success(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify package succeeds even if 1 of 3 endpoints fails."""
        service = _make_service(config, mock_cache, mock_limiter)

        async def _mock_get(path: str, **kwargs: object) -> httpx.Response:
            if "financial-metrics" in path:
                return _make_httpx_response(_SAMPLE_METRICS_RESPONSE)
            if "income-statements" in path:
                # Simulate failure
                return _make_httpx_response({"error": "Server Error"}, status_code=500)
            if "balance-sheets" in path:
                return _make_httpx_response(_SAMPLE_BALANCE_RESPONSE)
            return _make_httpx_response({}, status_code=404)

        with patch.object(service._client, "get", side_effect=_mock_get):
            result = await service.fetch_package("AAPL")

        assert result is not None
        assert result.metrics is not None
        assert result.income is None  # failed endpoint
        assert result.balance_sheet is not None
        await service.close()

    @pytest.mark.asyncio
    async def test_all_endpoints_fail_returns_none(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify package returns None when all 3 endpoints fail."""
        service = _make_service(config, mock_cache, mock_limiter)

        async def _mock_get(path: str, **kwargs: object) -> httpx.Response:
            return _make_httpx_response({"error": "Server Error"}, status_code=500)

        with patch.object(service._client, "get", side_effect=_mock_get):
            result = await service.fetch_package("AAPL")

        assert result is None
        await service.close()

    @pytest.mark.asyncio
    async def test_config_disabled_returns_none(
        self,
        disabled_config: FinancialDatasetsConfig,
        mock_cache: MagicMock,
        mock_limiter: MagicMock,
    ) -> None:
        """Verify fetch_package no-ops when disabled."""
        service = _make_service(disabled_config, mock_cache, mock_limiter)
        result = await service.fetch_package("AAPL")
        assert result is None
        await service.close()


# ---------------------------------------------------------------------------
# close() and rate limiter tests
# ---------------------------------------------------------------------------


class TestServiceLifecycle:
    """Tests for close() and rate limiter usage."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify close() calls httpx client aclose()."""
        service = _make_service(config, mock_cache, mock_limiter)

        with patch.object(service._client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await service.close()

        mock_aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limiter_used(
        self, config: FinancialDatasetsConfig, mock_cache: MagicMock, mock_limiter: MagicMock
    ) -> None:
        """Verify rate limiter context manager is entered during API calls."""
        service = _make_service(config, mock_cache, mock_limiter)
        response = _make_httpx_response(_SAMPLE_METRICS_RESPONSE)

        with patch.object(service._client, "get", new_callable=AsyncMock, return_value=response):
            await service.fetch_financial_metrics("AAPL")

        mock_limiter.__aenter__.assert_called()
        mock_limiter.__aexit__.assert_called()
        await service.close()
