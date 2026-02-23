"""Pre-flight health checks for all external dependencies.

Each check returns a typed ``HealthStatus`` with latency measurement.
``check_all()`` runs all checks concurrently — one failure never blocks the others.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime

import httpx
import yfinance as yf  # type: ignore[import-untyped]

from options_arena.models.config import ServiceConfig
from options_arena.models.health import HealthStatus

logger = logging.getLogger(__name__)


class HealthService:
    """Pre-flight health checker for external dependencies.

    Args:
        config: Service configuration with timeouts, Ollama host/model, etc.
    """

    def __init__(self, config: ServiceConfig) -> None:
        self._config = config
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

    async def check_ollama(self) -> HealthStatus:
        """Check Ollama availability and verify the configured model is present.

        Sends ``GET {ollama_host}/api/tags`` and inspects the response body
        for the configured model name.
        """
        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.get(f"{self._config.ollama_host}/api/tags"),
                timeout=self._config.ollama_timeout,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.status_code >= 500:
                logger.warning("Ollama health check failed: HTTP %d", response.status_code)
                return HealthStatus(
                    service_name="ollama",
                    available=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {response.status_code}",
                    checked_at=datetime.now(UTC),
                )

            # Parse the response to check for the configured model
            data = response.json()
            model_names: list[str] = [m.get("name", "") for m in data.get("models", [])]
            model_found = any(self._config.ollama_model in name for name in model_names)

            if not model_found:
                logger.warning(
                    "Ollama reachable but model '%s' not found. Available: %s",
                    self._config.ollama_model,
                    model_names,
                )
                return HealthStatus(
                    service_name="ollama",
                    available=False,
                    latency_ms=latency_ms,
                    error=f"model '{self._config.ollama_model}' not found",
                    checked_at=datetime.now(UTC),
                )

            logger.info("Ollama health check OK (%.1fms)", latency_ms)
            return HealthStatus(
                service_name="ollama",
                available=True,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning("Ollama health check failed: %s", exc)
            return HealthStatus(
                service_name="ollama",
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
                timeout=self._config.fred_timeout,
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
            self.check_ollama(),
            self.check_cboe(),
        ]
        service_names = ["yfinance", "fred", "ollama", "cboe"]
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
