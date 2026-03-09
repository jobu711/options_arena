"""Pre-flight health checks for all external dependencies.

Each check returns a typed ``HealthStatus`` with latency measurement.
``check_all()`` runs all checks concurrently — one failure never blocks the others.
"""

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import cast

import httpx
import yfinance as yf

from options_arena.models.config import FinancialDatasetsConfig, OpenBBConfig, ServiceConfig
from options_arena.models.health import HealthStatus
from options_arena.services.cache import ServiceCache
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class HealthService:
    """Pre-flight health checker for external dependencies.

    Args:
        config: Service configuration with timeouts, API keys, etc.
    """

    def __init__(
        self,
        config: ServiceConfig,
        *,
        openbb_config: OpenBBConfig | None = None,
        fd_config: FinancialDatasetsConfig | None = None,
        cache: object | None = None,
        limiter: object | None = None,
    ) -> None:
        self._config = config
        self._openbb_config = openbb_config
        self._fd_config = fd_config
        self._cache = cache
        self._limiter = limiter
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

    async def check_yfinance(self) -> HealthStatus:
        """Check yfinance availability by fetching a SPY fast_info snapshot.

        Wraps the synchronous yfinance call with ``asyncio.to_thread()``
        and bounds it with ``asyncio.wait_for()`` using the configured timeout.
        """
        start = time.monotonic()
        try:
            ticker = yf.Ticker("SPY")
            await asyncio.wait_for(
                asyncio.to_thread(lambda: ticker.fast_info),
                timeout=self._config.yfinance_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000
            logger.info("yfinance health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="yfinance",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("yfinance health check failed: %s", exc)
            return HealthStatus(
                service_name="yfinance",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_fred(self) -> HealthStatus:
        """Check FRED API reachability with an HTTP HEAD request."""
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.head("https://api.stlouisfed.org/fred/"),
                timeout=self._config.fred_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000
            # Accept any non-server-error status as "reachable"
            available = response.status_code < 500
            logger.info(
                "FRED health check %s (status=%d, %.1fms)",
                "OK" if available else "FAILED",
                response.status_code,
                latency_ms,
            )
            return HealthStatus(
                service_name="fred",
                available=available,
                latency_ms=latency_ms,
                error=None if available else f"HTTP {response.status_code}",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("FRED health check failed: %s", exc)
            return HealthStatus(
                service_name="fred",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_groq(self) -> HealthStatus:
        """Check Groq API availability by listing models.

        Checks if an API key is configured (config or ``GROQ_API_KEY`` env),
        then sends ``GET https://api.groq.com/openai/v1/models`` with Bearer token.
        """
        start = time.monotonic()

        # Resolve API key: config > env > None
        api_key: str | None = None
        if self._config.groq_api_key is not None:
            api_key = self._config.groq_api_key.get_secret_value()
        else:
            api_key = os.environ.get("GROQ_API_KEY")
        if api_key is None:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Groq health check failed: no API key configured")
            return HealthStatus(
                service_name="groq",
                available=False,
                latency_ms=latency_ms,
                error="no API key configured",
                checked_at=datetime.now(UTC),
            )

        try:
            response = await asyncio.wait_for(
                self._client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                ),
                timeout=self._config.health_check_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code == 401:
                logger.warning("Groq health check failed: invalid API key")
                return HealthStatus(
                    service_name="groq",
                    available=False,
                    latency_ms=latency_ms,
                    error="invalid API key (401)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code == 403:
                logger.warning("Groq health check failed: forbidden (403)")
                return HealthStatus(
                    service_name="groq",
                    available=False,
                    latency_ms=latency_ms,
                    error="forbidden (403)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code == 429:
                logger.warning("Groq health check: rate limited (429)")
                return HealthStatus(
                    service_name="groq",
                    available=True,
                    latency_ms=latency_ms,
                    error="rate limited (429)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code >= 500:
                logger.warning("Groq health check failed: HTTP %d", response.status_code)
                return HealthStatus(
                    service_name="groq",
                    available=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                    checked_at=datetime.now(UTC),
                )

            logger.info("Groq health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="groq",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Groq health check failed: %s", exc)
            return HealthStatus(
                service_name="groq",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_anthropic(self) -> HealthStatus:
        """Check Anthropic API availability by listing models.

        Checks if an API key is configured (config or ``ANTHROPIC_API_KEY`` env),
        then sends ``GET https://api.anthropic.com/v1/models`` with ``x-api-key`` header.
        """
        start = time.monotonic()

        # Resolve API key: config > env > None
        api_key: str | None = None
        if self._config.anthropic_api_key is not None:
            api_key = self._config.anthropic_api_key.get_secret_value()
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key is None:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Anthropic health check failed: no API key configured")
            return HealthStatus(
                service_name="anthropic",
                available=False,
                latency_ms=latency_ms,
                error="no API key configured",
                checked_at=datetime.now(UTC),
            )

        try:
            response = await asyncio.wait_for(
                self._client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                ),
                timeout=self._config.health_check_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code == 401:
                logger.warning("Anthropic health check failed: invalid API key")
                return HealthStatus(
                    service_name="anthropic",
                    available=False,
                    latency_ms=latency_ms,
                    error="invalid API key (401)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code == 403:
                logger.warning("Anthropic health check failed: forbidden (403)")
                return HealthStatus(
                    service_name="anthropic",
                    available=False,
                    latency_ms=latency_ms,
                    error="forbidden (403)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code == 429:
                logger.warning("Anthropic health check: rate limited (429)")
                return HealthStatus(
                    service_name="anthropic",
                    available=True,
                    latency_ms=latency_ms,
                    error="rate limited (429)",
                    checked_at=datetime.now(UTC),
                )

            if response.status_code >= 500:
                logger.warning("Anthropic health check failed: HTTP %d", response.status_code)
                return HealthStatus(
                    service_name="anthropic",
                    available=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                    checked_at=datetime.now(UTC),
                )

            logger.info("Anthropic health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="anthropic",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Anthropic health check failed: %s", exc)
            return HealthStatus(
                service_name="anthropic",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_cboe(self) -> HealthStatus:
        """Check CBOE CSV download endpoint reachability with HTTP HEAD."""
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.head("https://www.cboe.com/available_weeklys/"),
                timeout=self._config.cboe_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000
            available = response.status_code < 500
            logger.info(
                "CBOE health check %s (status=%d, %.1fms)",
                "OK" if available else "FAILED",
                response.status_code,
                latency_ms,
            )
            return HealthStatus(
                service_name="cboe",
                available=available,
                latency_ms=latency_ms,
                error=None if available else f"HTTP {response.status_code}",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("CBOE health check failed: %s", exc)
            return HealthStatus(
                service_name="cboe",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_openbb(self) -> HealthStatus:
        """Check OpenBB SDK availability via guarded import.

        Returns ``available=True`` if the ``openbb`` package is importable.
        Does NOT make a live API call — only checks SDK installation.
        """
        start = time.monotonic()
        try:
            from openbb import obb  # noqa: F401

            latency_ms = (time.monotonic() - start) * 1000
            logger.info("OpenBB health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="openbb",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except ImportError:
            latency_ms = (time.monotonic() - start) * 1000
            logger.info("OpenBB SDK not installed")
            return HealthStatus(
                service_name="openbb",
                available=False,
                latency_ms=latency_ms,
                error="OpenBB SDK not installed",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("OpenBB health check failed: %s", exc)
            return HealthStatus(
                service_name="openbb",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_intelligence(self) -> HealthStatus:
        """Check intelligence data availability via yfinance analyst price targets.

        Uses ``get_analyst_price_targets()`` for SPY as a lightweight smoke test.
        """
        start = time.monotonic()
        try:
            ticker = yf.Ticker("SPY")
            await asyncio.wait_for(
                asyncio.to_thread(ticker.get_analyst_price_targets),
                timeout=self._config.yfinance_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000
            logger.info("Intelligence health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="intelligence",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Intelligence health check failed: %s", exc)
            return HealthStatus(
                service_name="intelligence",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_cboe_chains(self) -> HealthStatus:
        """Test CBOE chain endpoint with a known ticker (AAPL).

        Returns ``available=False`` if CBOE chains are disabled in config,
        if the OpenBB SDK is not installed, or if the probe call fails.
        """
        if self._openbb_config is None or not self._openbb_config.cboe_chains_enabled:
            return HealthStatus(
                service_name="cboe_chains",
                available=False,
                error="CBOE chains disabled",
                checked_at=datetime.now(UTC),
            )

        if self._cache is None or self._limiter is None:
            return HealthStatus(
                service_name="cboe_chains",
                available=False,
                error="Cache/limiter not provided for CBOE health check",
                checked_at=datetime.now(UTC),
            )

        from options_arena.services.cboe_provider import CBOEChainProvider  # noqa: PLC0415

        provider = CBOEChainProvider(
            config=self._openbb_config,
            cache=cast(ServiceCache, self._cache),
            limiter=cast(RateLimiter, self._limiter),
        )
        if not provider.available:
            return HealthStatus(
                service_name="cboe_chains",
                available=False,
                error="OpenBB SDK not installed",
                checked_at=datetime.now(UTC),
            )

        start = time.monotonic()
        try:
            await provider.fetch_expirations("AAPL")
            latency_ms = (time.monotonic() - start) * 1000
            logger.info("CBOE chains health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="cboe_chains",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("CBOE chains health check failed: %s", exc)
            return HealthStatus(
                service_name="cboe_chains",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )

    async def check_financial_datasets(self) -> HealthStatus:
        """Check Financial Datasets API health by fetching AAPL metrics.

        Requires ``fd_config`` with ``enabled=True`` and an API key. Creates a
        temporary ``FinancialDatasetsService`` for the probe call.
        """
        if self._fd_config is None or not self._fd_config.enabled:
            return HealthStatus(
                service_name="financial_datasets",
                available=False,
                error="Financial Datasets disabled",
                checked_at=datetime.now(UTC),
            )
        if self._fd_config.api_key is None:
            return HealthStatus(
                service_name="financial_datasets",
                available=False,
                error="no API key configured",
                checked_at=datetime.now(UTC),
            )

        from options_arena.services.cache import ServiceCache  # noqa: PLC0415
        from options_arena.services.rate_limiter import RateLimiter  # noqa: PLC0415

        start = time.monotonic()
        svc: FinancialDatasetsService | None = None
        local_cache: ServiceCache | None = None
        try:
            # Use existing cache/limiter if provided, otherwise create minimal ones
            cache: ServiceCache
            if isinstance(self._cache, ServiceCache):
                cache = self._cache
            else:
                local_cache = ServiceCache(self._config)
                cache = local_cache
            limiter = (
                self._limiter
                if isinstance(self._limiter, RateLimiter)
                else RateLimiter(
                    self._config.rate_limit_rps, self._config.max_concurrent_requests
                )
            )

            svc = FinancialDatasetsService(
                config=self._fd_config,
                cache=cache,
                limiter=limiter,
            )

            result = await svc.fetch_financial_metrics("AAPL")
            latency_ms = (time.monotonic() - start) * 1000
            if result is not None:
                logger.info("Financial Datasets health check OK (%.1fms)", latency_ms)
                return HealthStatus(
                    service_name="financial_datasets",
                    available=True,
                    latency_ms=latency_ms,
                    checked_at=datetime.now(UTC),
                )
            logger.warning("Financial Datasets health check: no data returned")
            return HealthStatus(
                service_name="financial_datasets",
                available=False,
                latency_ms=latency_ms,
                error="No data returned",
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Financial Datasets health check failed: %s", exc)
            return HealthStatus(
                service_name="financial_datasets",
                available=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(UTC),
            )
        finally:
            if svc is not None:
                await svc.close()
            if local_cache is not None:
                await local_cache.close()

    async def check_all(self) -> list[HealthStatus]:
        """Run all health checks concurrently.

        Uses ``asyncio.gather(return_exceptions=True)`` so one failed check
        never blocks or cancels the others. If a check raises an unhandled
        exception (shouldn't happen — each check catches broadly), the
        exception is converted to a ``HealthStatus(available=False)``.
        """
        tasks = [
            self.check_yfinance(),
            self.check_fred(),
            self.check_groq(),
            self.check_anthropic(),
            self.check_cboe(),
            self.check_openbb(),
            self.check_cboe_chains(),
            self.check_intelligence(),
        ]
        service_names = [
            "yfinance",
            "fred",
            "groq",
            "anthropic",
            "cboe",
            "openbb",
            "cboe_chains",
            "intelligence",
        ]

        # Add Financial Datasets check when config is provided (method handles disabled/no-key)
        if self._fd_config is not None:
            tasks.append(self.check_financial_datasets())
            service_names.append("financial_datasets")
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[HealthStatus] = []
        for name, result in zip(service_names, raw_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("Unexpected exception from %s health check: %s", name, result)
                results.append(
                    HealthStatus(
                        service_name=name,
                        available=False,
                        error=str(result),
                        checked_at=datetime.now(UTC),
                    )
                )
            else:
                results.append(result)
        return results

    async def close(self) -> None:
        """Close the shared httpx client."""
        await self._client.aclose()
