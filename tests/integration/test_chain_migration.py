"""Integration tests for the CBOE chain migration (provider-abstracted pipeline).

Tests verify end-to-end wiring with mocked external dependencies:
  - Scan Phase 3 with CBOE provider → contracts with native Greeks
  - CBOE failure → yfinance fallback → contracts still returned
  - CBOE native Greeks bypass pricing/dispatch in scoring
  - bid_iv/ask_iv propagation from CBOE through to OptionContract
  - Debate path with CBOE chains
  - Full fallback chain (CBOE → yfinance → error)
  - Cutover configuration (cboe_chains_enabled default=True)
  - Backward compatibility regressions
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from options_arena.models.config import (
    AppSettings,
    OpenBBConfig,
    ServiceConfig,
)
from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
    SignalDirection,
)
from options_arena.models.filters import OptionsFilters
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import compute_greeks, recommend_contracts
from options_arena.services.cache import ServiceCache
from options_arena.services.cboe_provider import CBOEChainProvider
from options_arena.services.options_data import (
    OptionsDataService,
    YFinanceChainProvider,
)
from options_arena.services.rate_limiter import RateLimiter
from options_arena.utils.exceptions import DataSourceUnavailableError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FUTURE_EXP = date.today() + timedelta(days=45)


def _make_cboe_df(
    *,
    ticker: str = "AAPL",
    strikes: list[float] | None = None,
    with_greeks: bool = True,
    with_bid_ask_iv: bool = True,
) -> pd.DataFrame:
    """Build a DataFrame mimicking CBOE chain data from OpenBB.

    Columns match the CBOE provider's expectations: option_type, strike, bid,
    ask, last_price, volume, open_interest, implied_volatility, delta, gamma,
    theta, vega, rho, bid_iv, ask_iv, expiration.
    """
    if strikes is None:
        strikes = [180.0, 185.0, 190.0]

    rows = []
    for strike in strikes:
        for opt_type in ("call", "put"):
            row: dict[str, object] = {
                "option_type": opt_type,
                "strike": strike,
                "bid": 4.50 if opt_type == "call" else 3.20,
                "ask": 4.80 if opt_type == "call" else 3.50,
                "last_price": 4.65 if opt_type == "call" else 3.35,
                "volume": 1500,
                "open_interest": 12000,
                "implied_volatility": 0.285,
                "expiration": _FUTURE_EXP,
            }
            if with_greeks:
                delta = 0.35 if opt_type == "call" else -0.35
                row.update(
                    {
                        "delta": delta,
                        "gamma": 0.025,
                        "theta": -0.045,
                        "vega": 0.32,
                        "rho": 0.08 if opt_type == "call" else -0.08,
                    }
                )
            if with_bid_ask_iv:
                row.update(
                    {
                        "bid_iv": 0.28,
                        "ask_iv": 0.29,
                    }
                )
            rows.append(row)

    return pd.DataFrame(rows)


def _make_mock_obb_result(df: pd.DataFrame) -> MagicMock:
    """Create a mock OpenBB result with a .to_df() method."""
    result = MagicMock()
    result.to_df.return_value = df
    return result


def _make_yf_chain_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Build a DataFrame mimicking yfinance option chain columns."""
    columns = [
        "contractSymbol",
        "lastTradeDate",
        "strike",
        "lastPrice",
        "bid",
        "ask",
        "change",
        "percentChange",
        "volume",
        "openInterest",
        "impliedVolatility",
        "inTheMoney",
        "contractSize",
        "currency",
    ]
    full_rows = []
    for row in rows:
        full_row: dict[str, object] = {col: None for col in columns}
        full_row.update(row)
        full_rows.append(full_row)
    return pd.DataFrame(full_rows)


def _make_yf_option_chain_result(
    calls_rows: list[dict[str, object]],
    puts_rows: list[dict[str, object]],
) -> MagicMock:
    """Create a mock yfinance option_chain() result with .calls and .puts."""
    result = MagicMock()
    result.calls = _make_yf_chain_df(calls_rows)
    result.puts = _make_yf_chain_df(puts_rows)
    return result


def _make_contract(
    *,
    ticker: str = "AAPL",
    option_type: OptionType = OptionType.CALL,
    strike: str = "185.00",
    dte_days: int = 45,
    bid: str = "4.50",
    ask: str = "4.80",
    volume: int = 1500,
    open_interest: int = 12000,
    market_iv: float = 0.285,
    greeks: OptionGreeks | None = None,
    bid_iv: float | None = None,
    ask_iv: float | None = None,
    greeks_source: GreeksSource | None = None,
) -> OptionContract:
    """Factory for creating test OptionContract instances."""
    return OptionContract(
        ticker=ticker,
        option_type=option_type,
        strike=Decimal(strike),
        expiration=date.today() + timedelta(days=dte_days),
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal("4.65"),
        volume=volume,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=market_iv,
        greeks=greeks,
        bid_iv=bid_iv,
        ask_iv=ask_iv,
        greeks_source=greeks_source,
    )


def _cboe_greeks() -> OptionGreeks:
    """Create OptionGreeks as returned by CBOE (market-derived)."""
    return OptionGreeks(
        delta=0.35,
        gamma=0.025,
        theta=-0.045,
        vega=0.32,
        rho=0.08,
        pricing_model=PricingModel.BAW,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def service_config() -> ServiceConfig:
    """Default ServiceConfig."""
    return ServiceConfig()


@pytest.fixture()
def options_filters() -> OptionsFilters:
    """Default OptionsFilters with standard filters."""
    return OptionsFilters()


@pytest.fixture()
def cache(service_config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache (no SQLite)."""
    return ServiceCache(service_config, db_path=None)


@pytest.fixture()
def limiter() -> RateLimiter:
    """Fast rate limiter for tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


# ---------------------------------------------------------------------------
# TestChainMigrationScanPipeline
# ---------------------------------------------------------------------------


class TestChainMigrationScanPipeline:
    """Test scan Phase 3 with CBOE provider."""

    async def test_scan_with_cboe_provider(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify OptionsDataService with CBOE returns contracts with native Greeks."""
        cboe_df = _make_cboe_df(with_greeks=True)
        mock_result = _make_mock_obb_result(cboe_df)

        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb:
            mock_obb = MagicMock()
            mock_obb.derivatives.options.chains.return_value = mock_result
            mock_get_obb.return_value = mock_obb

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        assert len(contracts) > 0
        # CBOE contracts should have Greeks pre-populated
        for c in contracts:
            assert c.greeks is not None
            assert c.greeks_source == GreeksSource.MARKET

    async def test_scan_cboe_fallback_to_yfinance(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify CBOE failure falls back to yfinance, contracts still returned."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        yf_call_row = {
            "strike": 185.0,
            "lastPrice": 4.65,
            "bid": 4.50,
            "ask": 4.80,
            "volume": 1500,
            "openInterest": 12000,
            "impliedVolatility": 0.285,
        }
        yf_chain = _make_yf_option_chain_result([yf_call_row], [])

        with (
            patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb,
            patch("options_arena.services.options_data.yf") as mock_yf,
        ):
            # CBOE SDK is present but raises an error
            mock_obb = MagicMock()
            mock_obb.derivatives.options.chains.side_effect = RuntimeError("CBOE API down")
            mock_get_obb.return_value = mock_obb

            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = yf_chain
            mock_yf.Ticker.return_value = mock_ticker

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        # Should have fallen back to yfinance
        assert len(contracts) == 1
        assert contracts[0].strike == Decimal("185.0")
        # yfinance contracts have no Greeks
        assert contracts[0].greeks is None
        assert contracts[0].greeks_source is None

    async def test_scan_cboe_greeks_skip_dispatch(self) -> None:
        """Verify CBOE native Greeks bypass local computation in scoring.

        Tier 1 contracts (with pre-populated Greeks from CBOE) should NOT
        trigger calls to pricing/dispatch.option_greeks. Only Tier 2
        contracts (without Greeks) should call dispatch.
        """
        # Tier 1: CBOE contract with native Greeks
        cboe_contract = _make_contract(
            greeks=_cboe_greeks(),
            greeks_source=GreeksSource.MARKET,
        )

        # Tier 2: yfinance contract without Greeks
        yf_contract = _make_contract(
            strike="190.00",
            greeks=None,
            greeks_source=None,
        )

        with patch("options_arena.scoring.contracts.option_greeks") as mock_dispatch:
            mock_dispatch.return_value = OptionGreeks(
                delta=0.30,
                gamma=0.020,
                theta=-0.040,
                vega=0.28,
                rho=0.07,
                pricing_model=PricingModel.BAW,
            )

            result = compute_greeks(
                [cboe_contract, yf_contract],
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
            )

        # Both contracts should be in the result
        assert len(result) == 2

        # Tier 1 contract preserves CBOE Greeks
        tier1 = [c for c in result if c.strike == Decimal("185.00")][0]
        assert tier1.greeks is not None
        assert tier1.greeks.delta == pytest.approx(0.35)
        assert tier1.greeks_source == GreeksSource.MARKET

        # Tier 2 contract gets computed Greeks
        tier2 = [c for c in result if c.strike == Decimal("190.00")][0]
        assert tier2.greeks is not None
        assert tier2.greeks_source == GreeksSource.COMPUTED

        # pricing/dispatch.option_greeks was called only for the Tier 2 contract
        assert mock_dispatch.call_count == 1

    async def test_scan_bid_ask_iv_propagation(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify bid_iv/ask_iv flow from CBOE through to contract."""
        cboe_df = _make_cboe_df(with_greeks=True, with_bid_ask_iv=True)
        mock_result = _make_mock_obb_result(cboe_df)

        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb:
            mock_obb = MagicMock()
            mock_obb.derivatives.options.chains.return_value = mock_result
            mock_get_obb.return_value = mock_obb

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        assert len(contracts) > 0
        for c in contracts:
            assert c.bid_iv == pytest.approx(0.28, rel=1e-3)
            assert c.ask_iv == pytest.approx(0.29, rel=1e-3)


# ---------------------------------------------------------------------------
# TestChainMigrationDebatePath
# ---------------------------------------------------------------------------


class TestChainMigrationDebatePath:
    """Test debate path with CBOE chains."""

    async def test_debate_with_cboe_chains(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify debate path gets contracts with CBOE Greeks.

        Simulates the chain-fetching portion of the debate path:
        OptionsDataService → contracts with greeks → ready for scoring.
        """
        cboe_df = _make_cboe_df(with_greeks=True)
        mock_result = _make_mock_obb_result(cboe_df)

        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb:
            mock_obb = MagicMock()
            mock_obb.derivatives.options.chains.return_value = mock_result
            mock_get_obb.return_value = mock_obb

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        # Contracts have native Greeks — scoring Tier 1 will preserve them
        assert all(c.greeks is not None for c in contracts)
        assert all(c.greeks_source == GreeksSource.MARKET for c in contracts)

        # Greeks values are valid
        for c in contracts:
            assert c.greeks is not None
            assert -1.0 <= c.greeks.delta <= 1.0
            assert c.greeks.gamma >= 0.0
            assert c.greeks.vega >= 0.0

    async def test_debate_cboe_fallback(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify debate falls back to yfinance on CBOE failure."""
        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        yf_call_row = {
            "strike": 185.0,
            "lastPrice": 4.65,
            "bid": 4.50,
            "ask": 4.80,
            "volume": 1500,
            "openInterest": 12000,
            "impliedVolatility": 0.285,
        }
        yf_chain = _make_yf_option_chain_result([yf_call_row], [])

        with (
            patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb,
            patch("options_arena.services.options_data.yf") as mock_yf,
        ):
            # CBOE SDK unavailable
            mock_get_obb.return_value = None

            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = yf_chain
            mock_yf.Ticker.return_value = mock_ticker

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        # Fell back to yfinance — no Greeks, needs Tier 2 computation
        assert len(contracts) == 1
        assert contracts[0].greeks is None


# ---------------------------------------------------------------------------
# TestChainMigrationFallback
# ---------------------------------------------------------------------------


class TestChainMigrationFallback:
    """Test full fallback chain."""

    async def test_full_fallback_chain(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify CBOE -> yfinance -> error flow end-to-end.

        When both CBOE and yfinance fail, DataSourceUnavailableError is raised.
        """
        openbb_config = OpenBBConfig(cboe_chains_enabled=True)

        with (
            patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb,
            patch("options_arena.services.options_data.yf") as mock_yf,
        ):
            # CBOE present but fails
            mock_obb = MagicMock()
            mock_obb.derivatives.options.chains.side_effect = RuntimeError("CBOE down")
            mock_get_obb.return_value = mock_obb

            # yfinance also fails
            mock_ticker = MagicMock()
            mock_ticker.option_chain.side_effect = RuntimeError("yfinance down")
            mock_yf.Ticker.return_value = mock_ticker

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            with pytest.raises(DataSourceUnavailableError):
                await service.fetch_chain("AAPL", _FUTURE_EXP)


# ---------------------------------------------------------------------------
# TestCutoverConfig
# ---------------------------------------------------------------------------


class TestCutoverConfig:
    """Test cutover configuration."""

    def test_cboe_chains_enabled_default_true(self) -> None:
        """Verify cboe_chains_enabled defaults to True after cutover."""
        config = OpenBBConfig()
        assert config.cboe_chains_enabled is True

    def test_env_override_disables_cboe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify ARENA_OPENBB__CBOE_CHAINS_ENABLED=false disables CBOE."""
        monkeypatch.setenv("ARENA_OPENBB__CBOE_CHAINS_ENABLED", "false")
        settings = AppSettings()
        assert settings.openbb.cboe_chains_enabled is False

    def test_yfinance_fallback_always_present(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify yfinance is always in provider list regardless of config."""
        # With CBOE enabled (default after cutover) but SDK not available
        openbb_config = OpenBBConfig()  # cboe_chains_enabled=True
        assert openbb_config.cboe_chains_enabled is True

        with patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb:
            mock_get_obb.return_value = None  # No OpenBB SDK

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

        # yfinance should be present
        yf_providers = [p for p in service._providers if isinstance(p, YFinanceChainProvider)]
        assert len(yf_providers) == 1

    def test_cboe_plus_yfinance_when_sdk_available(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify both CBOE and yfinance when SDK is available."""
        openbb_config = OpenBBConfig()  # cboe_chains_enabled=True

        with patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb:
            mock_obb = MagicMock()
            mock_get_obb.return_value = mock_obb

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

        # CBOE first, yfinance second
        assert len(service._providers) == 2
        assert isinstance(service._providers[0], CBOEChainProvider)
        assert isinstance(service._providers[1], YFinanceChainProvider)


# ---------------------------------------------------------------------------
# TestRegressionSuite
# ---------------------------------------------------------------------------


class TestRegressionSuite:
    """Regression tests for backward compatibility."""

    async def test_no_openbb_sdk_identical_behavior(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify system with no OpenBB SDK behaves identically to pre-migration.

        When the OpenBB SDK is not installed, cboe_chains_enabled=True has no
        effect — the system falls back to yfinance-only mode.
        """
        openbb_config = OpenBBConfig()  # cboe_chains_enabled=True (new default)

        yf_call_row = {
            "strike": 185.0,
            "lastPrice": 4.65,
            "bid": 4.50,
            "ask": 4.80,
            "volume": 1500,
            "openInterest": 12000,
            "impliedVolatility": 0.285,
        }
        yf_chain = _make_yf_option_chain_result([yf_call_row], [])

        with (
            patch("options_arena.services.cboe_provider._get_obb") as mock_get_obb,
            patch("options_arena.services.options_data.yf") as mock_yf,
        ):
            mock_get_obb.return_value = None  # No OpenBB SDK

            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = yf_chain
            mock_yf.Ticker.return_value = mock_ticker

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        # Identical to pre-migration: yfinance contracts, no Greeks
        assert len(contracts) == 1
        assert contracts[0].greeks is None
        assert contracts[0].greeks_source is None
        assert contracts[0].bid_iv is None
        assert contracts[0].ask_iv is None
        assert contracts[0].market_iv == pytest.approx(0.285, rel=1e-4)
        assert contracts[0].exercise_style == ExerciseStyle.AMERICAN

    async def test_cboe_disabled_identical_behavior(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify cboe_chains_enabled=False produces identical results.

        Explicitly disabling CBOE should produce yfinance-only behavior,
        even when OpenBB SDK is installed.
        """
        openbb_config = OpenBBConfig(cboe_chains_enabled=False)

        yf_call_row = {
            "strike": 190.0,
            "lastPrice": 3.50,
            "bid": 3.30,
            "ask": 3.70,
            "volume": 800,
            "openInterest": 5000,
            "impliedVolatility": 0.30,
        }
        yf_chain = _make_yf_option_chain_result([yf_call_row], [])

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = yf_chain
            mock_yf.Ticker.return_value = mock_ticker

            service = OptionsDataService(
                service_config,
                options_filters,
                cache,
                limiter,
                openbb_config=openbb_config,
            )

            contracts = await service.fetch_chain("AAPL", _FUTURE_EXP)

        # Only yfinance provider in list
        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)

        # yfinance-only behavior
        assert len(contracts) == 1
        assert contracts[0].greeks is None
        assert contracts[0].greeks_source is None

    def test_option_contract_backward_compat(self) -> None:
        """Verify OptionContract without new fields constructs identically.

        Constructing an OptionContract without bid_iv, ask_iv, greeks_source
        should work with defaults (all None) — same as pre-migration.
        """
        contract = OptionContract(
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date.today() + timedelta(days=45),
            bid=Decimal("4.50"),
            ask=Decimal("4.80"),
            last=Decimal("4.65"),
            volume=1500,
            open_interest=12000,
            exercise_style=ExerciseStyle.AMERICAN,
            market_iv=0.285,
        )

        # New fields default to None
        assert contract.bid_iv is None
        assert contract.ask_iv is None
        assert contract.greeks_source is None
        assert contract.greeks is None

        # Existing computed fields still work
        assert contract.mid == Decimal("4.65")
        assert contract.spread == Decimal("0.30")

    async def test_recommend_contracts_with_cboe_greeks(self) -> None:
        """Verify recommend_contracts pipeline works with CBOE pre-populated Greeks.

        When all contracts have Tier 1 Greeks, pricing/dispatch should NOT
        be called and the full pipeline should return a recommendation.
        """
        greeks = _cboe_greeks()
        contracts = [
            _make_contract(
                strike="180.00",
                greeks=greeks,
                greeks_source=GreeksSource.MARKET,
            ),
            _make_contract(
                strike="185.00",
                greeks=greeks,
                greeks_source=GreeksSource.MARKET,
            ),
            _make_contract(
                strike="190.00",
                greeks=greeks,
                greeks_source=GreeksSource.MARKET,
            ),
        ]

        with patch("options_arena.scoring.contracts.option_greeks") as mock_dispatch:
            result = recommend_contracts(
                contracts,
                direction=SignalDirection.BULLISH,
                spot=185.0,
                risk_free_rate=0.05,
                dividend_yield=0.005,
            )

        # pricing/dispatch never called — all Tier 1
        assert mock_dispatch.call_count == 0

        # Got a recommendation
        assert len(result) >= 1
        recommended = result[0]
        assert recommended.greeks is not None
        assert recommended.greeks_source == GreeksSource.MARKET

    async def test_no_openbb_config_at_all(
        self,
        service_config: ServiceConfig,
        options_filters: OptionsFilters,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify omitting openbb_config entirely gives yfinance-only behavior.

        This is the backward-compatible constructor pattern used by
        existing code that predates the CBOE migration.
        """
        yf_call_row = {
            "strike": 200.0,
            "lastPrice": 2.50,
            "bid": 2.30,
            "ask": 2.70,
            "volume": 500,
            "openInterest": 3000,
            "impliedVolatility": 0.25,
        }
        yf_chain = _make_yf_option_chain_result([yf_call_row], [])

        with patch("options_arena.services.options_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.option_chain.return_value = yf_chain
            mock_yf.Ticker.return_value = mock_ticker

            # No openbb_config at all — pre-migration constructor
            service = OptionsDataService(service_config, options_filters, cache, limiter)

            contracts = await service.fetch_chain("SPY", _FUTURE_EXP)

        # Only yfinance
        assert len(service._providers) == 1
        assert isinstance(service._providers[0], YFinanceChainProvider)
        assert len(contracts) == 1
        assert contracts[0].greeks is None
