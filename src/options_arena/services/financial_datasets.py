"""Financial Datasets AI service for fundamental data enrichment.

Fetches financial metrics, income statements, and balance sheets from the
financialdatasets.ai REST API. All methods follow the never-raises contract --
errors are logged and ``None`` is returned. Uses cache-first strategy with
configurable TTL and token-bucket rate limiting.

Inherits from :class:`ServiceBase[FinancialDatasetsConfig]` for standardised
cache, limiter, and logging infrastructure.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from options_arena.models.config import FinancialDatasetsConfig
from options_arena.models.financial_datasets import (
    BalanceSheetData,
    FinancialDatasetsPackage,
    FinancialMetricsData,
    IncomeStatementData,
)
from options_arena.services.base import ServiceBase
from options_arena.services.cache import ServiceCache
from options_arena.services.helpers import safe_float, safe_int
from options_arena.services.rate_limiter import RateLimiter

# Cache key prefixes
_CACHE_PREFIX_METRICS: str = "fd:metrics"
_CACHE_PREFIX_INCOME: str = "fd:income"
_CACHE_PREFIX_BALANCE: str = "fd:balance"


class FinancialDatasetsService(ServiceBase[FinancialDatasetsConfig]):
    """Enrichment service fetching fundamental data from financialdatasets.ai.

    All public methods follow the never-raises contract: exceptions are
    caught, logged at WARNING, and ``None`` is returned.

    Inherits from :class:`ServiceBase[FinancialDatasetsConfig]` for
    standardised ``_config``, ``_cache``, ``_limiter``, ``_log``, and
    ``close()``.

    Args:
        config: Financial Datasets configuration (timeouts, TTLs, API key).
        cache: Two-tier service cache for caching responses.
        limiter: Rate limiter for controlling request frequency.
    """

    def __init__(
        self,
        config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        super().__init__(config, cache, limiter)
        # Narrow type: this service always requires a limiter (never None).
        self._limiter: RateLimiter = limiter
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={
                "X-API-KEY": config.api_key.get_secret_value() if config.api_key else "",
            },
            timeout=httpx.Timeout(config.request_timeout),
        )

    async def fetch_financial_metrics(self, ticker: str) -> FinancialMetricsData | None:
        """Fetch point-in-time financial metrics for a ticker.

        Returns ``None`` if the service is disabled, no API key is configured,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or self._config.api_key is None:
            return None

        try:
            cache_key = f"{_CACHE_PREFIX_METRICS}:{ticker}:ttm"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                self._log.debug("Financial Datasets metrics cache hit for %s", ticker)
                return FinancialMetricsData.model_validate_json(cached)

            raw = await self._api_get(
                "/api/v1/financial-metrics",
                params={"ticker": ticker, "period": "ttm", "limit": "1"},
            )
            if raw is None:
                return None

            items: list[dict[str, Any]] = raw.get("financial_metrics", [])
            if not items:
                self._log.warning("Financial Datasets returned empty metrics for %s", ticker)
                return None

            data = items[0]
            result = FinancialMetricsData(
                pe_ratio=safe_float(data.get("pe_ratio")),
                forward_pe=safe_float(data.get("forward_pe")),
                peg_ratio=safe_float(data.get("peg_ratio")),
                price_to_book=safe_float(data.get("price_to_book")),
                price_to_sales=safe_float(data.get("price_to_sales")),
                enterprise_value_to_ebitda=safe_float(data.get("enterprise_value_to_ebitda")),
                enterprise_value_to_revenue=safe_float(data.get("enterprise_value_to_revenue")),
                gross_margin=safe_float(data.get("gross_margin")),
                operating_margin=safe_float(data.get("operating_margin")),
                net_margin=safe_float(data.get("net_margin")),
                profit_margin=safe_float(data.get("profit_margin")),
                revenue_growth=safe_float(data.get("revenue_growth")),
                earnings_growth=safe_float(data.get("earnings_growth")),
                return_on_equity=safe_float(data.get("return_on_equity")),
                return_on_assets=safe_float(data.get("return_on_assets")),
                return_on_capital=safe_float(data.get("return_on_capital")),
                debt_to_equity=safe_float(data.get("debt_to_equity")),
                current_ratio=safe_float(data.get("current_ratio")),
                eps_diluted=safe_float(data.get("eps_diluted")),
                free_cash_flow_yield=safe_float(data.get("free_cash_flow_yield")),
                dividend_yield=safe_float(data.get("dividend_yield")),
            )

            await self._cache.set(
                cache_key,
                result.model_dump_json().encode(),
                ttl=self._config.cache_ttl,
            )
            self._log.debug("Fetched and cached Financial Datasets metrics for %s", ticker)
            return result

        except Exception:
            self._log.warning(
                "Financial Datasets metrics fetch failed for %s",
                ticker,
                exc_info=True,
            )
            return None

    async def fetch_income_statement(self, ticker: str) -> IncomeStatementData | None:
        """Fetch point-in-time income statement data for a ticker.

        Returns ``None`` if the service is disabled, no API key is configured,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or self._config.api_key is None:
            return None

        try:
            cache_key = f"{_CACHE_PREFIX_INCOME}:{ticker}:ttm"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                self._log.debug("Financial Datasets income cache hit for %s", ticker)
                return IncomeStatementData.model_validate_json(cached)

            raw = await self._api_get(
                "/api/v1/income-statements",
                params={"ticker": ticker, "period": "ttm", "limit": "1"},
            )
            if raw is None:
                return None

            items: list[dict[str, Any]] = raw.get("income_statements", [])
            if not items:
                self._log.warning(
                    "Financial Datasets returned empty income statement for %s", ticker
                )
                return None

            data = items[0]
            result = IncomeStatementData(
                revenue=safe_float(data.get("revenue")),
                gross_profit=safe_float(data.get("gross_profit")),
                operating_income=safe_float(data.get("operating_income")),
                net_income=safe_float(data.get("net_income")),
                eps_diluted=safe_float(data.get("eps_diluted")),
                gross_margin=safe_float(data.get("gross_margin")),
                operating_margin=safe_float(data.get("operating_margin")),
                net_margin=safe_float(data.get("net_margin")),
            )

            await self._cache.set(
                cache_key,
                result.model_dump_json().encode(),
                ttl=self._config.cache_ttl,
            )
            self._log.debug(
                "Fetched and cached Financial Datasets income statement for %s", ticker
            )
            return result

        except Exception:
            self._log.warning(
                "Financial Datasets income statement fetch failed for %s",
                ticker,
                exc_info=True,
            )
            return None

    async def fetch_balance_sheet(self, ticker: str) -> BalanceSheetData | None:
        """Fetch point-in-time balance sheet data for a ticker.

        Returns ``None`` if the service is disabled, no API key is configured,
        or any error occurs during the fetch.
        """
        if not self._config.enabled or self._config.api_key is None:
            return None

        try:
            cache_key = f"{_CACHE_PREFIX_BALANCE}:{ticker}:ttm"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                self._log.debug("Financial Datasets balance sheet cache hit for %s", ticker)
                return BalanceSheetData.model_validate_json(cached)

            raw = await self._api_get(
                "/api/v1/balance-sheets",
                params={"ticker": ticker, "period": "ttm", "limit": "1"},
            )
            if raw is None:
                return None

            items: list[dict[str, Any]] = raw.get("balance_sheets", [])
            if not items:
                self._log.warning("Financial Datasets returned empty balance sheet for %s", ticker)
                return None

            data = items[0]
            result = BalanceSheetData(
                total_assets=safe_float(data.get("total_assets")),
                total_liabilities=safe_float(data.get("total_liabilities")),
                total_equity=safe_float(data.get("total_equity")),
                total_debt=safe_float(data.get("total_debt")),
                total_cash=safe_float(data.get("total_cash")),
                current_assets=safe_float(data.get("current_assets")),
                current_liabilities=safe_float(data.get("current_liabilities")),
                shares_outstanding=safe_int(data.get("shares_outstanding")),
            )

            await self._cache.set(
                cache_key,
                result.model_dump_json().encode(),
                ttl=self._config.cache_ttl,
            )
            self._log.debug("Fetched and cached Financial Datasets balance sheet for %s", ticker)
            return result

        except Exception:
            self._log.warning(
                "Financial Datasets balance sheet fetch failed for %s",
                ticker,
                exc_info=True,
            )
            return None

    async def fetch_package(self, ticker: str) -> FinancialDatasetsPackage | None:
        """Fetch all financial data for a ticker in parallel.

        Runs ``fetch_financial_metrics``, ``fetch_income_statement``, and
        ``fetch_balance_sheet`` concurrently via ``asyncio.gather``. Returns a
        ``FinancialDatasetsPackage`` if at least one component succeeded, or
        ``None`` if all three fail.
        """
        if not self._config.enabled or self._config.api_key is None:
            return None

        try:
            tasks = [
                self.fetch_financial_metrics(ticker),
                self.fetch_income_statement(ticker),
                self.fetch_balance_sheet(ticker),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            metrics: FinancialMetricsData | None = None
            income: IncomeStatementData | None = None
            balance: BalanceSheetData | None = None

            if isinstance(results[0], FinancialMetricsData):
                metrics = results[0]
            if isinstance(results[1], IncomeStatementData):
                income = results[1]
            if isinstance(results[2], BalanceSheetData):
                balance = results[2]

            if metrics is None and income is None and balance is None:
                self._log.warning("All Financial Datasets endpoints failed for %s", ticker)
                return None

            return FinancialDatasetsPackage(
                ticker=ticker,
                metrics=metrics,
                income=income,
                balance_sheet=balance,
                fetched_at=datetime.now(UTC),
            )

        except Exception:
            self._log.warning(
                "Financial Datasets package fetch failed for %s",
                ticker,
                exc_info=True,
            )
            return None

    async def close(self) -> None:
        """Close the httpx client."""
        await self._client.aclose()
        await super().close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _api_get(
        self,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any] | None:
        """Make a rate-limited, timeout-bounded GET request.

        Returns parsed JSON as a dict, or ``None`` on any error.
        """
        try:
            async with self._limiter:
                response = await asyncio.wait_for(
                    self._client.get(path, params=params),
                    timeout=self._config.request_timeout,
                )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except TimeoutError:
            self._log.warning("Financial Datasets API timeout for %s", path)
            return None
        except httpx.HTTPStatusError as exc:
            self._log.warning(
                "Financial Datasets API HTTP %d for %s",
                exc.response.status_code,
                path,
            )
            return None
        except Exception:
            self._log.warning("Financial Datasets API request failed for %s", path, exc_info=True)
            return None
