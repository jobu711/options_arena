"""Tests for services.base — ServiceBase mixin infrastructure.

Tests cover init, close, _cached_fetch, _retried_fetch, _yf_call, and
generic config compatibility. No real API calls — all async operations
are mocked.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict

from options_arena.models.config import ServiceConfig
from options_arena.services.base import ServiceBase
from options_arena.services.cache import ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import (
    DataSourceUnavailableError,
    InsufficientDataError,
    TickerNotFoundError,
)

# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------


class _SampleConfig(BaseModel):
    """Minimal config for testing generic type parameter."""

    timeout: float = 5.0


class _AltConfig(BaseModel):
    """Alternative config to verify generic flexibility."""

    enabled: bool = True
    url: str = "https://example.com"


class _SampleModel(BaseModel):
    """Pydantic model for cache serde tests."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    value: float


class _ConcreteService(ServiceBase[ServiceConfig]):
    """Concrete subclass using ServiceConfig for tests."""


class _CustomCloseService(ServiceBase[_SampleConfig]):
    """Service with overridden close()."""

    def __init__(
        self,
        config: _SampleConfig,
        cache: ServiceCache,
        limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(config, cache, limiter)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def service_config() -> ServiceConfig:
    return ServiceConfig()


@pytest.fixture
def sample_config() -> _SampleConfig:
    return _SampleConfig()


@pytest.fixture
def mock_cache() -> MagicMock:
    """Mock ServiceCache with async get/set."""
    cache = MagicMock(spec=ServiceCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(rate=100.0, max_concurrent=10)


@pytest.fixture
def service(
    service_config: ServiceConfig,
    mock_cache: MagicMock,
    limiter: RateLimiter,
) -> _ConcreteService:
    return _ConcreteService(service_config, mock_cache, limiter)


@pytest.fixture
def service_no_limiter(
    service_config: ServiceConfig,
    mock_cache: MagicMock,
) -> _ConcreteService:
    return _ConcreteService(service_config, mock_cache)


# ===========================================================================
# TestServiceBaseInit
# ===========================================================================


class TestServiceBaseInit:
    """Tests for ServiceBase.__init__ — attribute storage and defaults."""

    def test_config_stored(
        self, service_config: ServiceConfig, mock_cache: MagicMock, limiter: RateLimiter
    ) -> None:
        svc = _ConcreteService(service_config, mock_cache, limiter)
        assert svc._config is service_config

    def test_cache_stored(
        self, service_config: ServiceConfig, mock_cache: MagicMock, limiter: RateLimiter
    ) -> None:
        svc = _ConcreteService(service_config, mock_cache, limiter)
        assert svc._cache is mock_cache

    def test_limiter_stored(
        self, service_config: ServiceConfig, mock_cache: MagicMock, limiter: RateLimiter
    ) -> None:
        svc = _ConcreteService(service_config, mock_cache, limiter)
        assert svc._limiter is limiter

    def test_limiter_defaults_none(
        self, service_config: ServiceConfig, mock_cache: MagicMock
    ) -> None:
        svc = _ConcreteService(service_config, mock_cache)
        assert svc._limiter is None

    def test_logger_created(self, service_config: ServiceConfig, mock_cache: MagicMock) -> None:
        svc = _ConcreteService(service_config, mock_cache)
        assert isinstance(svc._log, logging.Logger)
        assert svc._log.name == type(svc).__module__


# ===========================================================================
# TestServiceBaseClose
# ===========================================================================


class TestServiceBaseClose:
    """Tests for ServiceBase.close() — default no-op and override."""

    @pytest.mark.asyncio
    async def test_default_close_is_noop(self, service: _ConcreteService) -> None:
        # Should not raise
        await service.close()

    @pytest.mark.asyncio
    async def test_close_can_be_overridden(
        self, sample_config: _SampleConfig, mock_cache: MagicMock
    ) -> None:
        svc = _CustomCloseService(sample_config, mock_cache)
        assert not svc.closed
        await svc.close()
        assert svc.closed


# ===========================================================================
# TestCachedFetch
# ===========================================================================


class TestCachedFetch:
    """Tests for ServiceBase._cached_fetch — cache-first with model serde."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_deserialized(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        model = _SampleModel(ticker="AAPL", value=42.0)
        mock_cache.get = AsyncMock(return_value=model.model_dump_json().encode("utf-8"))

        factory = AsyncMock()
        result = await service._cached_fetch("test:key", _SampleModel, factory, ttl=300)

        assert result == model
        factory.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_factory(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        model = _SampleModel(ticker="MSFT", value=99.5)
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value=model)

        result = await service._cached_fetch("test:miss", _SampleModel, factory, ttl=60)

        assert result == model
        factory.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        model = _SampleModel(ticker="GOOG", value=10.0)
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value=model)

        await service._cached_fetch("test:store", _SampleModel, factory, ttl=120)

        mock_cache.set.assert_awaited_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "test:store"
        assert call_args[1]["ttl"] == 120
        # Verify the bytes are valid JSON for the model
        stored_bytes: bytes = call_args[0][1]
        roundtripped = _SampleModel.model_validate_json(stored_bytes)
        assert roundtripped == model

    @pytest.mark.asyncio
    async def test_ttl_passed_to_cache(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        model = _SampleModel(ticker="X", value=1.0)
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value=model)

        await service._cached_fetch("test:ttl", _SampleModel, factory, ttl=999)

        mock_cache.set.assert_awaited_once()
        assert mock_cache.set.call_args[1]["ttl"] == 999

    @pytest.mark.asyncio
    async def test_custom_deserializer_used_on_hit(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        raw_bytes = b'{"ticker":"TSLA","value":777.0}'
        mock_cache.get = AsyncMock(return_value=raw_bytes)

        custom = MagicMock(return_value=_SampleModel(ticker="TSLA", value=777.0))

        result = await service._cached_fetch(
            "test:custom",
            _SampleModel,
            AsyncMock(),
            ttl=60,
            deserializer=custom,
        )

        custom.assert_called_once_with(raw_bytes)
        assert result.ticker == "TSLA"
        assert result.value == pytest.approx(777.0)

    @pytest.mark.asyncio
    async def test_factory_exception_propagates(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(side_effect=DataSourceUnavailableError("test failure"))

        with pytest.raises(DataSourceUnavailableError, match="test failure"):
            await service._cached_fetch("test:err", _SampleModel, factory, ttl=60)

    @pytest.mark.asyncio
    async def test_model_serde_roundtrip(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        """Verify that model_dump_json -> model_validate_json roundtrip preserves data."""
        model = _SampleModel(ticker="NVDA", value=123.456)
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value=model)

        # First call: cache miss -> factory called -> result stored
        result = await service._cached_fetch("test:rt", _SampleModel, factory, ttl=60)
        assert result == model

        # Now simulate cache hit with the bytes that were stored
        stored_bytes = mock_cache.set.call_args[0][1]
        mock_cache.get = AsyncMock(return_value=stored_bytes)
        factory2 = AsyncMock()

        result2 = await service._cached_fetch("test:rt", _SampleModel, factory2, ttl=60)
        assert result2 == model
        factory2.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_key_forwarded(
        self, service: _ConcreteService, mock_cache: MagicMock
    ) -> None:
        mock_cache.get = AsyncMock(return_value=None)
        factory = AsyncMock(return_value=_SampleModel(ticker="X", value=0.0))

        await service._cached_fetch("yf:quote:SPY:v1", _SampleModel, factory, ttl=60)

        mock_cache.get.assert_awaited_once_with("yf:quote:SPY:v1")
        assert mock_cache.set.call_args[0][0] == "yf:quote:SPY:v1"


# ===========================================================================
# TestRetriedFetch
# ===========================================================================


class TestRetriedFetch:
    """Tests for ServiceBase._retried_fetch — rate-limited retry wrapper."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self, service: _ConcreteService) -> None:
        fn = AsyncMock(return_value="ok")
        result = await service._retried_fetch(fn, "arg1")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self, service: _ConcreteService) -> None:
        fn = AsyncMock(
            side_effect=[
                DataSourceUnavailableError("transient"),
                "recovered",
            ]
        )
        result = await service._retried_fetch(fn, max_attempts=3)
        assert result == "recovered"
        assert fn.await_count == 2  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_passes_limiter(
        self,
        service_config: ServiceConfig,
        mock_cache: MagicMock,
    ) -> None:
        limiter = RateLimiter(rate=100.0, max_concurrent=10)
        svc = _ConcreteService(service_config, mock_cache, limiter)

        with patch(
            "options_arena.services.base.fetch_with_limiter_retry",
            new_callable=AsyncMock,
            return_value="done",
        ) as mock_retry:
            result = await svc._retried_fetch(AsyncMock(), "a", max_attempts=2)
            assert result == "done"
            assert mock_retry.call_args[1]["limiter"] is limiter
            assert mock_retry.call_args[1]["max_attempts"] == 2

    @pytest.mark.asyncio
    async def test_respects_max_attempts(self, service: _ConcreteService) -> None:
        fn = AsyncMock(side_effect=DataSourceUnavailableError("fail"))
        with pytest.raises(DataSourceUnavailableError, match="fail"):
            await service._retried_fetch(fn, max_attempts=2)

    @pytest.mark.asyncio
    async def test_no_limiter_raises_runtime_error(
        self, service_no_limiter: _ConcreteService
    ) -> None:
        with pytest.raises(RuntimeError, match="requires a RateLimiter"):
            await service_no_limiter._retried_fetch(AsyncMock())


# ===========================================================================
# TestYfCall
# ===========================================================================


class TestYfCall:
    """Tests for ServiceBase._yf_call — sync yfinance wrapping."""

    @pytest.mark.asyncio
    async def test_success(self, service: _ConcreteService) -> None:
        def sync_fn(x: int) -> int:
            return x * 2

        result = await service._yf_call(sync_fn, 21, timeout=5.0)
        assert result == 42  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_timeout_raises_data_source_unavailable(self, service: _ConcreteService) -> None:
        import time

        def slow_fn() -> None:
            time.sleep(5)

        with pytest.raises(DataSourceUnavailableError, match="timeout"):
            await service._yf_call(slow_fn, timeout=0.05)

    @pytest.mark.asyncio
    async def test_generic_exception_wrapped(self, service: _ConcreteService) -> None:
        def bad_fn() -> None:
            raise ValueError("something broke")

        with pytest.raises(DataSourceUnavailableError, match="something broke"):
            await service._yf_call(bad_fn, timeout=5.0)

    @pytest.mark.asyncio
    async def test_args_and_kwargs_forwarded(self, service: _ConcreteService) -> None:
        def fn_with_args(a: int, b: int, *, multiplier: int = 1) -> int:
            return (a + b) * multiplier

        result = await service._yf_call(fn_with_args, 3, 4, timeout=5.0, multiplier=10)
        assert result == 70  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_timeout_is_explicit(self, service: _ConcreteService) -> None:
        """_yf_call requires timeout as a keyword argument — no default."""

        def noop() -> str:
            return "ok"

        # Must pass timeout explicitly
        result = await service._yf_call(noop, timeout=1.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_data_fetch_error_not_double_wrapped(self, service: _ConcreteService) -> None:
        """DataFetchError subclasses are re-raised as-is, not wrapped."""

        def raises_ticker_not_found() -> None:
            raise TickerNotFoundError("BADTICKER: not found")

        with pytest.raises(TickerNotFoundError, match="BADTICKER"):
            await service._yf_call(raises_ticker_not_found, timeout=5.0)

    @pytest.mark.asyncio
    async def test_insufficient_data_error_not_double_wrapped(
        self, service: _ConcreteService
    ) -> None:
        """InsufficientDataError (a DataFetchError subclass) re-raised as-is."""

        def raises_insufficient() -> None:
            raise InsufficientDataError("no data")

        with pytest.raises(InsufficientDataError, match="no data"):
            await service._yf_call(raises_insufficient, timeout=5.0)


# ===========================================================================
# TestGenericConfig
# ===========================================================================


class TestGenericConfig:
    """Tests that ServiceBase[ConfigT] accepts different config types."""

    def test_with_service_config(self, mock_cache: MagicMock, limiter: RateLimiter) -> None:
        config = ServiceConfig()
        svc: ServiceBase[ServiceConfig] = ServiceBase(config, mock_cache, limiter)
        assert svc._config is config
        assert isinstance(svc._config, ServiceConfig)

    def test_with_custom_config(self, mock_cache: MagicMock) -> None:
        config = _SampleConfig(timeout=10.0)
        svc: ServiceBase[_SampleConfig] = ServiceBase(config, mock_cache)
        assert svc._config is config
        assert svc._config.timeout == pytest.approx(10.0)

    def test_with_alt_config(self, mock_cache: MagicMock) -> None:
        config = _AltConfig(enabled=False, url="https://alt.example.com")
        svc: ServiceBase[_AltConfig] = ServiceBase(config, mock_cache)
        assert svc._config is config
        assert svc._config.enabled is False
        assert svc._config.url == "https://alt.example.com"
