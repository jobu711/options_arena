"""Tests for CBOEChainProvider — CBOE chain data via OpenBB Platform SDK."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any  # noqa: ANN401 — test helper dicts need Any for mixed-type values
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import OpenBBConfig
from options_arena.models.enums import ExerciseStyle, GreeksSource, OptionType, PricingModel
from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider, _validate_greeks
from options_arena.services.options_data import ChainProvider
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> OpenBBConfig:
    """OpenBBConfig with CBOE chains enabled."""
    return OpenBBConfig(cboe_chains_enabled=True, request_timeout=10)


@pytest.fixture
def config_disabled() -> OpenBBConfig:
    """OpenBBConfig with CBOE chains disabled."""
    return OpenBBConfig(cboe_chains_enabled=False, request_timeout=10)


@pytest.fixture
def cache() -> ServiceCache:
    """In-memory-only cache (no SQLite)."""
    return ServiceCache(config=MagicMock(), db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Fast rate limiter for tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


@pytest.fixture
def mock_obb() -> MagicMock:
    """Mock OpenBB SDK instance."""
    return MagicMock()


def _make_cboe_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame mimicking CBOE chain columns from OpenBB.

    Includes all common columns. Test rows can override any column.
    """
    base_columns = [
        "option_type",
        "strike",
        "expiration",
        "bid",
        "ask",
        "last_price",
        "volume",
        "open_interest",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
    ]
    full_rows: list[dict[str, Any]] = []
    for row in rows:
        full_row: dict[str, Any] = {col: None for col in base_columns}
        full_row.update(row)
        full_rows.append(full_row)
    return pd.DataFrame(full_rows)


def _make_obb_result(df: pd.DataFrame) -> MagicMock:
    """Create a mock OBBject with .to_df() returning the given DataFrame."""
    result = MagicMock()
    result.to_df.return_value = df
    return result


# ---------------------------------------------------------------------------
# TestChainProviderProtocol
# ---------------------------------------------------------------------------


class TestCBOEProtocolConformance:
    """Verify CBOEChainProvider satisfies ChainProvider protocol."""

    @patch("options_arena.services.cboe_provider._get_obb")
    def test_satisfies_chain_provider_protocol(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """CBOEChainProvider is recognized as ChainProvider at runtime."""
        mock_get_obb.return_value = MagicMock()
        provider = CBOEChainProvider(config, cache, limiter)
        assert isinstance(provider, ChainProvider)

    @patch("options_arena.services.cboe_provider._get_obb")
    def test_has_required_methods(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """CBOEChainProvider has fetch_expirations and fetch_chain methods."""
        mock_get_obb.return_value = MagicMock()
        provider = CBOEChainProvider(config, cache, limiter)
        assert hasattr(provider, "fetch_expirations")
        assert hasattr(provider, "fetch_chain")
        assert callable(provider.fetch_expirations)
        assert callable(provider.fetch_chain)


# ---------------------------------------------------------------------------
# TestAvailableProperty
# ---------------------------------------------------------------------------


class TestAvailableProperty:
    """Verify the available property correctly reflects SDK + config state."""

    @patch("options_arena.services.cboe_provider._get_obb")
    def test_available_when_sdk_present_and_enabled(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """available is True when SDK is installed and cboe_chains_enabled=True."""
        mock_get_obb.return_value = MagicMock()
        provider = CBOEChainProvider(config, cache, limiter)
        assert provider.available is True

    @patch("options_arena.services.cboe_provider._get_obb")
    def test_not_available_when_sdk_missing(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """available is False when OpenBB SDK is not installed."""
        mock_get_obb.return_value = None
        provider = CBOEChainProvider(config, cache, limiter)
        assert provider.available is False

    @patch("options_arena.services.cboe_provider._get_obb")
    def test_not_available_when_chains_disabled(
        self,
        mock_get_obb: MagicMock,
        config_disabled: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """available is False when cboe_chains_enabled=False even if SDK present."""
        mock_get_obb.return_value = MagicMock()
        provider = CBOEChainProvider(config_disabled, cache, limiter)
        assert provider.available is False


# ---------------------------------------------------------------------------
# TestFetchChain
# ---------------------------------------------------------------------------


class TestFetchChain:
    """Tests for CBOEChainProvider.fetch_chain field mapping."""

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_happy_path(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """fetch_chain returns OptionContract list from CBOE DataFrame."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        call_row: dict[str, Any] = {
            "option_type": "call",
            "strike": 185.0,
            "expiration": "2026-04-18",
            "bid": 5.30,
            "ask": 5.70,
            "last_price": 5.50,
            "volume": 500,
            "open_interest": 2000,
            "implied_volatility": 0.32,
            "delta": 0.55,
            "gamma": 0.03,
            "theta": -0.05,
            "vega": 0.15,
            "rho": 0.02,
        }
        put_row: dict[str, Any] = {
            "option_type": "put",
            "strike": 185.0,
            "expiration": "2026-04-18",
            "bid": 3.00,
            "ask": 3.40,
            "last_price": 3.20,
            "volume": 300,
            "open_interest": 1500,
            "implied_volatility": 0.28,
            "delta": -0.45,
            "gamma": 0.03,
            "theta": -0.04,
            "vega": 0.14,
            "rho": -0.01,
        }
        df = _make_cboe_df([call_row, put_row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("AAPL", date(2026, 4, 18))

        assert len(contracts) == 2

        call = contracts[0]
        assert call.ticker == "AAPL"
        assert call.option_type == OptionType.CALL
        assert call.strike == Decimal("185.0")
        assert call.expiration == date(2026, 4, 18)
        assert call.exercise_style == ExerciseStyle.AMERICAN
        assert call.bid == Decimal("5.3")
        assert call.ask == Decimal("5.7")
        assert call.volume == 500
        assert call.open_interest == 2000
        assert call.market_iv == pytest.approx(0.32, rel=1e-3)

        put = contracts[1]
        assert put.option_type == OptionType.PUT
        assert put.strike == Decimal("185.0")

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_with_greeks(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When CBOE provides valid Greeks, they are mapped with MARKET source."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 200.0,
            "expiration": "2026-05-15",
            "bid": 8.00,
            "ask": 8.50,
            "volume": 100,
            "open_interest": 1000,
            "implied_volatility": 0.25,
            "delta": 0.50,
            "gamma": 0.02,
            "theta": -0.06,
            "vega": 0.20,
            "rho": 0.03,
        }
        df = _make_cboe_df([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("MSFT", date(2026, 5, 15))

        assert len(contracts) == 1
        c = contracts[0]
        assert c.greeks is not None
        assert c.greeks.delta == pytest.approx(0.50, abs=1e-6)
        assert c.greeks.gamma == pytest.approx(0.02, abs=1e-6)
        assert c.greeks.theta == pytest.approx(-0.06, abs=1e-6)
        assert c.greeks.vega == pytest.approx(0.20, abs=1e-6)
        assert c.greeks.rho == pytest.approx(0.03, abs=1e-6)
        assert c.greeks.pricing_model == PricingModel.BAW
        assert c.greeks_source == GreeksSource.MARKET

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_partial_greeks_yields_none(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When some Greeks are missing (None), greeks and greeks_source are None."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 150.0,
            "expiration": "2026-06-19",
            "bid": 4.00,
            "ask": 4.50,
            "volume": 200,
            "open_interest": 800,
            "implied_volatility": 0.30,
            "delta": 0.45,
            "gamma": 0.025,
            "theta": None,  # missing
            "vega": 0.18,
            "rho": None,  # missing
        }
        df = _make_cboe_df([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("GOOG", date(2026, 6, 19))

        assert len(contracts) == 1
        assert contracts[0].greeks is None
        assert contracts[0].greeks_source is None

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_bid_ask_iv(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """bid_iv and ask_iv are populated when columns exist in CBOE data."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "put",
            "strike": 170.0,
            "expiration": "2026-04-18",
            "bid": 2.50,
            "ask": 3.00,
            "volume": 50,
            "open_interest": 400,
            "implied_volatility": 0.35,
            "bid_iv": 0.33,
            "ask_iv": 0.37,
            "delta": -0.30,
            "gamma": 0.02,
            "theta": -0.03,
            "vega": 0.12,
            "rho": -0.01,
        }
        # Build manually to include bid_iv/ask_iv columns
        df = pd.DataFrame([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("AMZN", date(2026, 4, 18))

        assert len(contracts) == 1
        c = contracts[0]
        assert c.bid_iv == pytest.approx(0.33, rel=1e-3)
        assert c.ask_iv == pytest.approx(0.37, rel=1e-3)

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_no_bid_ask_iv_columns(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """When bid_iv/ask_iv columns are absent, they are set to None."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 180.0,
            "expiration": "2026-04-18",
            "bid": 6.00,
            "ask": 6.50,
            "volume": 150,
            "open_interest": 600,
            "implied_volatility": 0.28,
            "delta": 0.55,
            "gamma": 0.03,
            "theta": -0.05,
            "vega": 0.16,
            "rho": 0.02,
        }
        # Standard _make_cboe_df does NOT include bid_iv/ask_iv columns
        df = _make_cboe_df([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("META", date(2026, 4, 18))

        assert len(contracts) == 1
        assert contracts[0].bid_iv is None
        assert contracts[0].ask_iv is None

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_empty_dataframe(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Empty DataFrame from CBOE returns empty contract list."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        df = pd.DataFrame()
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("EMPTY", date(2026, 4, 18))

        assert contracts == []

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_sdk_error_raises_unavailable(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """SDK exceptions map to DataSourceUnavailableError."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb
        mock_obb.derivatives.options.chains.side_effect = RuntimeError("SDK boom")

        provider = CBOEChainProvider(config, cache, limiter)

        with pytest.raises(DataSourceUnavailableError, match="CBOE via OpenBB"):
            await provider.fetch_chain("ERR", date(2026, 4, 18))

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_sdk_not_installed_raises(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """fetch_chain raises DataSourceUnavailableError when SDK is None."""
        mock_get_obb.return_value = None
        provider = CBOEChainProvider(config, cache, limiter)

        with pytest.raises(DataSourceUnavailableError, match="not installed"):
            await provider.fetch_chain("AAPL", date(2026, 4, 18))

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_chains_disabled_raises(
        self,
        mock_get_obb: MagicMock,
        config_disabled: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """fetch_chain raises DataSourceUnavailableError when chains disabled."""
        mock_get_obb.return_value = MagicMock()
        provider = CBOEChainProvider(config_disabled, cache, limiter)

        with pytest.raises(DataSourceUnavailableError, match="not enabled"):
            await provider.fetch_chain("AAPL", date(2026, 4, 18))

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_cache_hit(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Second call to fetch_chain uses cached data, not OpenBB SDK."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 250.0,
            "expiration": "2026-04-18",
            "bid": 10.0,
            "ask": 10.5,
            "volume": 100,
            "open_interest": 500,
            "implied_volatility": 0.25,
        }
        df = _make_cboe_df([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)

        # First call — hits SDK
        result1 = await provider.fetch_chain("CACHE", date(2026, 4, 18))
        # Second call — should use cache
        result2 = await provider.fetch_chain("CACHE", date(2026, 4, 18))

        # SDK called only once (the second call uses cache)
        assert mock_obb.derivatives.options.chains.call_count == 1
        assert len(result1) == len(result2)
        assert result1[0].strike == result2[0].strike

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_filters_by_expiration(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Only contracts matching the requested expiration are returned."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row_match: dict[str, Any] = {
            "option_type": "call",
            "strike": 200.0,
            "expiration": "2026-04-18",
            "bid": 5.0,
            "ask": 5.5,
            "volume": 100,
            "open_interest": 500,
            "implied_volatility": 0.25,
        }
        row_other: dict[str, Any] = {
            "option_type": "call",
            "strike": 210.0,
            "expiration": "2026-05-16",
            "bid": 3.0,
            "ask": 3.5,
            "volume": 50,
            "open_interest": 300,
            "implied_volatility": 0.22,
        }
        df = _make_cboe_df([row_match, row_other])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("FILT", date(2026, 4, 18))

        assert len(contracts) == 1
        assert contracts[0].strike == Decimal("200.0")

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_invalid_strike_skipped(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Rows with invalid strikes (zero, negative, None) are skipped."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        good_row: dict[str, Any] = {
            "option_type": "call",
            "strike": 150.0,
            "expiration": "2026-04-18",
            "bid": 4.0,
            "ask": 4.5,
            "volume": 100,
            "open_interest": 500,
            "implied_volatility": 0.30,
        }
        bad_row: dict[str, Any] = {
            "option_type": "call",
            "strike": 0.0,
            "expiration": "2026-04-18",
            "bid": 1.0,
            "ask": 1.5,
            "volume": 10,
            "open_interest": 50,
            "implied_volatility": 0.20,
        }
        df = _make_cboe_df([good_row, bad_row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("SKIP", date(2026, 4, 18))

        assert len(contracts) == 1
        assert contracts[0].strike == Decimal("150.0")

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_chain_all_american(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """All contracts from CBOE are ExerciseStyle.AMERICAN (U.S. equities)."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        rows = [
            {
                "option_type": "call",
                "strike": 100.0,
                "expiration": "2026-04-18",
                "bid": 2.0,
                "ask": 2.5,
                "volume": 50,
                "open_interest": 200,
                "implied_volatility": 0.20,
            },
            {
                "option_type": "put",
                "strike": 100.0,
                "expiration": "2026-04-18",
                "bid": 1.5,
                "ask": 2.0,
                "volume": 40,
                "open_interest": 150,
                "implied_volatility": 0.22,
            },
        ]
        df = _make_cboe_df(rows)
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("SPY", date(2026, 4, 18))

        for c in contracts:
            assert c.exercise_style == ExerciseStyle.AMERICAN


# ---------------------------------------------------------------------------
# TestFetchExpirations
# ---------------------------------------------------------------------------


class TestFetchExpirations:
    """Tests for CBOEChainProvider.fetch_expirations."""

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_expirations_happy_path(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """fetch_expirations extracts unique sorted dates from the chain."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        rows = [
            {"option_type": "call", "strike": 100.0, "expiration": "2026-05-16"},
            {"option_type": "call", "strike": 110.0, "expiration": "2026-04-18"},
            {"option_type": "put", "strike": 100.0, "expiration": "2026-05-16"},
            {"option_type": "call", "strike": 120.0, "expiration": "2026-06-19"},
        ]
        df = _make_cboe_df(rows)
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        expirations = await provider.fetch_expirations("AAPL")

        assert expirations == [
            date(2026, 4, 18),
            date(2026, 5, 16),
            date(2026, 6, 19),
        ]
        for d in expirations:
            assert isinstance(d, date)

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_expirations_sdk_not_installed(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """fetch_expirations raises when SDK is not installed."""
        mock_get_obb.return_value = None
        provider = CBOEChainProvider(config, cache, limiter)

        with pytest.raises(DataSourceUnavailableError, match="not installed"):
            await provider.fetch_expirations("AAPL")

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_fetch_expirations_cache_hit(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Second call to fetch_expirations uses cached data."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        rows = [
            {"option_type": "call", "strike": 100.0, "expiration": "2026-04-18"},
        ]
        df = _make_cboe_df(rows)
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)

        result1 = await provider.fetch_expirations("CACHED")
        result2 = await provider.fetch_expirations("CACHED")

        assert mock_obb.derivatives.options.chains.call_count == 1
        assert result1 == result2


# ---------------------------------------------------------------------------
# TestValidateGreeks (unit tests for the helper)
# ---------------------------------------------------------------------------


class TestValidateGreeks:
    """Tests for the _validate_greeks helper function."""

    def test_valid_greeks(self) -> None:
        """All five valid Greeks produce OptionGreeks with BAW pricing model."""
        result = _validate_greeks(0.50, 0.03, -0.05, 0.15, 0.02)
        assert result is not None
        assert result.delta == pytest.approx(0.50, abs=1e-6)
        assert result.gamma == pytest.approx(0.03, abs=1e-6)
        assert result.theta == pytest.approx(-0.05, abs=1e-6)
        assert result.vega == pytest.approx(0.15, abs=1e-6)
        assert result.rho == pytest.approx(0.02, abs=1e-6)
        assert result.pricing_model == PricingModel.BAW

    def test_missing_delta_returns_none(self) -> None:
        """Missing delta (None) results in None."""
        assert _validate_greeks(None, 0.03, -0.05, 0.15, 0.02) is None

    def test_missing_gamma_returns_none(self) -> None:
        """Missing gamma (None) results in None."""
        assert _validate_greeks(0.50, None, -0.05, 0.15, 0.02) is None

    def test_missing_theta_returns_none(self) -> None:
        """Missing theta (None) results in None."""
        assert _validate_greeks(0.50, 0.03, None, 0.15, 0.02) is None

    def test_missing_vega_returns_none(self) -> None:
        """Missing vega (None) results in None."""
        assert _validate_greeks(0.50, 0.03, -0.05, None, 0.02) is None

    def test_missing_rho_returns_none(self) -> None:
        """Missing rho (None) results in None."""
        assert _validate_greeks(0.50, 0.03, -0.05, 0.15, None) is None

    def test_delta_out_of_range_returns_none(self) -> None:
        """Delta > 1.0 fails sanity check."""
        assert _validate_greeks(1.5, 0.03, -0.05, 0.15, 0.02) is None

    def test_delta_negative_out_of_range_returns_none(self) -> None:
        """Delta < -1.0 fails sanity check."""
        assert _validate_greeks(-1.5, 0.03, -0.05, 0.15, 0.02) is None

    def test_negative_gamma_returns_none(self) -> None:
        """Negative gamma fails sanity check."""
        assert _validate_greeks(0.50, -0.01, -0.05, 0.15, 0.02) is None

    def test_negative_vega_returns_none(self) -> None:
        """Negative vega fails sanity check."""
        assert _validate_greeks(0.50, 0.03, -0.05, -0.01, 0.02) is None

    def test_nan_delta_returns_none(self) -> None:
        """NaN delta fails finite check."""
        assert _validate_greeks(float("nan"), 0.03, -0.05, 0.15, 0.02) is None

    def test_inf_theta_returns_none(self) -> None:
        """Inf theta fails finite check."""
        assert _validate_greeks(0.50, 0.03, float("inf"), 0.15, 0.02) is None

    def test_inf_rho_returns_none(self) -> None:
        """Inf rho fails finite check."""
        assert _validate_greeks(0.50, 0.03, -0.05, 0.15, float("inf")) is None

    def test_put_delta_negative_valid(self) -> None:
        """Negative delta for puts is valid within [-1.0, 0.0]."""
        result = _validate_greeks(-0.45, 0.03, -0.04, 0.14, -0.01)
        assert result is not None
        assert result.delta == pytest.approx(-0.45, abs=1e-6)

    def test_zero_greeks_valid(self) -> None:
        """All-zero Greeks pass validation (deep OTM edge case)."""
        result = _validate_greeks(0.0, 0.0, 0.0, 0.0, 0.0)
        assert result is not None


# ---------------------------------------------------------------------------
# TestMarketIVMapping
# ---------------------------------------------------------------------------


class TestMarketIVMapping:
    """Tests for market_iv computation from CBOE data."""

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_market_iv_from_implied_volatility(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """market_iv uses implied_volatility column when present."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 100.0,
            "expiration": "2026-04-18",
            "bid": 2.0,
            "ask": 2.5,
            "volume": 50,
            "open_interest": 200,
            "implied_volatility": 0.42,
        }
        df = _make_cboe_df([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("IV", date(2026, 4, 18))

        assert contracts[0].market_iv == pytest.approx(0.42, rel=1e-3)

    @patch("options_arena.services.cboe_provider._get_obb")
    async def test_market_iv_fallback_to_bid_ask_mid(
        self,
        mock_get_obb: MagicMock,
        config: OpenBBConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """market_iv falls back to (bid_iv + ask_iv) / 2 when implied_volatility is None."""
        mock_obb = MagicMock()
        mock_get_obb.return_value = mock_obb

        row: dict[str, Any] = {
            "option_type": "call",
            "strike": 100.0,
            "expiration": "2026-04-18",
            "bid": 2.0,
            "ask": 2.5,
            "volume": 50,
            "open_interest": 200,
            "implied_volatility": None,
            "bid_iv": 0.30,
            "ask_iv": 0.40,
        }
        df = pd.DataFrame([row])
        mock_obb.derivatives.options.chains.return_value = _make_obb_result(df)

        provider = CBOEChainProvider(config, cache, limiter)
        contracts = await provider.fetch_chain("IVMID", date(2026, 4, 18))

        assert contracts[0].market_iv == pytest.approx(0.35, rel=1e-3)
