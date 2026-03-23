"""Tests for ``_fetch_ticker_data`` helper extracted from ``process_ticker_options``.

Covers:
  - Happy path: contracts fetched, metadata enriched, ``filtered_out=False``.
  - Earnings proximity filter: ``filtered_out=True``, no chain fetch.
  - Market-cap tier filter: ``filtered_out=True``, chain fetched but excluded.
  - No earnings filter (``exclude_near_earnings_days=None``): concurrent earnings fetch.
  - Chain/info fetch failure: re-raises exception.
  - Metadata upsert failure: non-fatal, continues.
  - Empty chain: ``all_contracts`` empty, ``filtered_out=False``.
  - Sector/industry enrichment from metadata.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from options_arena.models import (
    IndicatorSignals,
    MarketCapTier,
    SignalDirection,
    TickerScore,
)
from options_arena.models.filters import OptionsFilters, UniverseFilters
from options_arena.models.market_data import TickerInfo
from options_arena.models.metadata import TickerMetadata
from options_arena.scan.phase_options import _fetch_ticker_data, _TickerData
from options_arena.services.options_data import ExpirationChain
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a minimal TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=80.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
    )


def _make_ticker_info(
    ticker: str = "AAPL",
    *,
    market_cap_tier: MarketCapTier | None = MarketCapTier.LARGE,
) -> TickerInfo:
    """Create a TickerInfo with sensible defaults."""
    return TickerInfo(
        ticker=ticker,
        company_name="Apple Inc.",
        sector="Information Technology",
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("200.00"),
        fifty_two_week_low=Decimal("140.00"),
        dividend_yield=0.005,
        market_cap_tier=market_cap_tier,
    )


def _make_chain(ticker: str = "AAPL", n_contracts: int = 2) -> list[ExpirationChain]:
    """Create a list of ExpirationChains with ``n_contracts`` contracts."""
    expiration = date.today() + timedelta(days=45)
    contracts = [
        make_option_contract(ticker=ticker, expiration=expiration) for _ in range(n_contracts)
    ]
    return [ExpirationChain(expiration=expiration, contracts=contracts)]


def _make_metadata(ticker: str = "AAPL") -> TickerMetadata:
    """Create a TickerMetadata with sensible defaults."""
    return TickerMetadata(
        ticker=ticker,
        sector="Information Technology",
        industry_group="Technology Hardware & Equipment",
        market_cap_tier=MarketCapTier.LARGE,
        last_updated=datetime.now(UTC),
    )


def _make_mocks(
    ticker: str = "AAPL",
    *,
    ticker_info: TickerInfo | None = None,
    chains: list[ExpirationChain] | None = None,
    earnings_date: date | None = None,
    metadata: TickerMetadata | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    """Create mocked services and map_yfinance_fn.

    Returns (market_data, options_data, repository, map_yfinance_fn).
    """
    mock_market_data = AsyncMock()
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=earnings_date)
    mock_market_data.fetch_ticker_info = AsyncMock(
        return_value=ticker_info or _make_ticker_info(ticker)
    )

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(
        return_value=chains if chains is not None else _make_chain(ticker)
    )

    mock_repository = AsyncMock()
    mock_repository.upsert_ticker_metadata = AsyncMock()

    mock_map_yfinance = MagicMock(return_value=metadata or _make_metadata(ticker))

    return mock_market_data, mock_options_data, mock_repository, mock_map_yfinance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchTickerDataHappyPath:
    """Happy-path tests for _fetch_ticker_data."""

    async def test_returns_contracts_and_ticker_info(self) -> None:
        """Verify happy path: contracts fetched, not filtered out."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert isinstance(result, _TickerData)
        assert result.filtered_out is False
        assert result.ticker_info is not None
        assert result.ticker_info.ticker == "AAPL"
        assert len(result.all_contracts) == 2
        assert result.entry_stock_price == Decimal("185.50")

    async def test_enriches_company_name(self) -> None:
        """Verify ticker_score.company_name is set from ticker_info."""
        ts = _make_ticker_score()
        assert ts.company_name is None
        market, options, repo, map_fn = _make_mocks()

        await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert ts.company_name == "Apple Inc."

    async def test_enriches_sector_and_industry_group(self) -> None:
        """Verify sector and industry_group are enriched from metadata."""
        ts = _make_ticker_score()
        assert ts.sector is None
        assert ts.industry_group is None

        metadata = _make_metadata()
        market, options, repo, map_fn = _make_mocks(metadata=metadata)

        await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert ts.sector == "Information Technology"
        assert ts.industry_group == "Technology Hardware & Equipment"

    async def test_upserts_metadata_to_repository(self) -> None:
        """Verify metadata is upserted to repository."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()

        await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        repo.upsert_ticker_metadata.assert_awaited_once()


class TestFetchTickerDataEarningsFilter:
    """Earnings proximity filter tests."""

    async def test_near_earnings_returns_filtered_out(self) -> None:
        """Verify ticker near earnings is filtered out."""
        ts = _make_ticker_score()
        tomorrow = date.today() + timedelta(days=1)
        market, options, repo, map_fn = _make_mocks(earnings_date=tomorrow)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is True
        assert result.all_contracts == []
        assert result.earnings_date == tomorrow
        assert result.entry_stock_price is None
        assert result.ticker_info is None
        # Chain fetch should NOT have been called
        options.fetch_chain_all_expirations.assert_not_awaited()

    async def test_earnings_on_today_triggers_filter(self) -> None:
        """Verify earnings on today (0 days) triggers filter."""
        ts = _make_ticker_score()
        today = date.today()
        market, options, repo, map_fn = _make_mocks(earnings_date=today)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is True

    async def test_past_earnings_does_not_trigger_filter(self) -> None:
        """Verify past earnings date does not trigger filter."""
        ts = _make_ticker_score()
        yesterday = date.today() - timedelta(days=1)
        market, options, repo, map_fn = _make_mocks(earnings_date=yesterday)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False

    async def test_distant_earnings_not_filtered(self) -> None:
        """Verify ticker with distant earnings proceeds normally."""
        ts = _make_ticker_score()
        far_date = date.today() + timedelta(days=30)
        market, options, repo, map_fn = _make_mocks(earnings_date=far_date)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=7),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False
        assert result.earnings_date == far_date

    async def test_no_earnings_filter_fetches_concurrently(self) -> None:
        """Verify exclude_near_earnings_days=None triggers concurrent fetch."""
        ts = _make_ticker_score()
        some_date = date.today() + timedelta(days=15)
        market, options, repo, map_fn = _make_mocks(earnings_date=some_date)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=None),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False
        # Earnings should have been fetched (as part of gather)
        assert result.earnings_date == some_date

    async def test_earnings_fetch_failure_non_fatal(self) -> None:
        """Verify earnings fetch failure is non-fatal, proceeds to chain fetch."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()
        market.fetch_earnings_date = AsyncMock(side_effect=RuntimeError("API error"))

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(exclude_near_earnings_days=3),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        # Should proceed despite earnings failure
        assert result.filtered_out is False
        assert result.earnings_date is None


class TestFetchTickerDataMarketCapFilter:
    """Market-cap tier filter tests."""

    async def test_excluded_market_cap_tier_returns_filtered_out(self) -> None:
        """Verify ticker excluded by market-cap tier filter."""
        ts = _make_ticker_score()
        info = _make_ticker_info(market_cap_tier=MarketCapTier.SMALL)
        market, options, repo, map_fn = _make_mocks(ticker_info=info)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(market_cap_tiers=[MarketCapTier.LARGE]),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is True
        assert result.all_contracts == []
        assert result.entry_stock_price == Decimal("185.50")
        assert result.ticker_info is not None

    async def test_matching_market_cap_tier_not_filtered(self) -> None:
        """Verify ticker with matching market-cap tier proceeds normally."""
        ts = _make_ticker_score()
        info = _make_ticker_info(market_cap_tier=MarketCapTier.LARGE)
        market, options, repo, map_fn = _make_mocks(ticker_info=info)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(market_cap_tiers=[MarketCapTier.LARGE]),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False

    async def test_empty_market_cap_tiers_filter_accepts_all(self) -> None:
        """Verify empty market_cap_tiers allows all tickers through."""
        ts = _make_ticker_score()
        info = _make_ticker_info(market_cap_tier=MarketCapTier.MICRO)
        market, options, repo, map_fn = _make_mocks(ticker_info=info)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(market_cap_tiers=[]),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False

    async def test_none_market_cap_tier_not_filtered(self) -> None:
        """Verify ticker with None market_cap_tier is not filtered."""
        ts = _make_ticker_score()
        info = _make_ticker_info(market_cap_tier=None)
        market, options, repo, map_fn = _make_mocks(ticker_info=info)

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(market_cap_tiers=[MarketCapTier.LARGE]),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False


class TestFetchTickerDataFailures:
    """Failure handling tests."""

    async def test_chain_fetch_failure_re_raises(self) -> None:
        """Verify chain fetch failure propagates as exception."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()
        options.fetch_chain_all_expirations = AsyncMock(
            side_effect=RuntimeError("chain fetch error")
        )

        with pytest.raises(RuntimeError, match="chain fetch error"):
            await _fetch_ticker_data(
                ts,
                market_data=market,
                options_data=options,
                repository=repo,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                map_yfinance_fn=map_fn,
            )

    async def test_ticker_info_failure_re_raises(self) -> None:
        """Verify ticker info fetch failure propagates as exception."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()
        market.fetch_ticker_info = AsyncMock(side_effect=RuntimeError("info fetch error"))

        with pytest.raises(RuntimeError, match="info fetch error"):
            await _fetch_ticker_data(
                ts,
                market_data=market,
                options_data=options,
                repository=repo,
                options_filters=OptionsFilters(),
                universe_filters=UniverseFilters(),
                map_yfinance_fn=map_fn,
            )

    async def test_metadata_upsert_failure_non_fatal(self) -> None:
        """Verify metadata upsert failure is non-fatal."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks()
        repo.upsert_ticker_metadata = AsyncMock(side_effect=RuntimeError("DB error"))

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        # Should succeed despite metadata upsert failure
        assert result.filtered_out is False
        assert len(result.all_contracts) == 2


class TestFetchTickerDataEmptyChain:
    """Tests for empty chain scenario."""

    async def test_empty_chain_returns_no_contracts(self) -> None:
        """Verify empty chain results in empty all_contracts."""
        ts = _make_ticker_score()
        market, options, repo, map_fn = _make_mocks(chains=[])

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert result.filtered_out is False
        assert result.all_contracts == []
        assert result.ticker_info is not None
        assert result.entry_stock_price == Decimal("185.50")


class TestFetchTickerDataContractFlattening:
    """Tests for contract flattening across expirations."""

    async def test_multiple_expirations_flattened(self) -> None:
        """Verify contracts from multiple expirations are flattened."""
        ts = _make_ticker_score()
        exp1 = date.today() + timedelta(days=30)
        exp2 = date.today() + timedelta(days=60)
        chain1 = ExpirationChain(
            expiration=exp1,
            contracts=[make_option_contract(expiration=exp1)],
        )
        chain2 = ExpirationChain(
            expiration=exp2,
            contracts=[
                make_option_contract(expiration=exp2),
                make_option_contract(expiration=exp2, strike=Decimal("160.00")),
            ],
        )
        market, options, repo, map_fn = _make_mocks(chains=[chain1, chain2])

        result = await _fetch_ticker_data(
            ts,
            market_data=market,
            options_data=options,
            repository=repo,
            options_filters=OptionsFilters(),
            universe_filters=UniverseFilters(),
            map_yfinance_fn=map_fn,
        )

        assert len(result.all_contracts) == 3


class TestTickerDataFrozen:
    """Verify _TickerData is immutable."""

    def test_frozen_dataclass(self) -> None:
        """Verify _TickerData rejects attribute mutation."""
        td = _TickerData(
            all_contracts=[],
            ticker_info=None,
            earnings_date=None,
            entry_stock_price=None,
            filtered_out=True,
        )
        with pytest.raises(AttributeError):
            td.filtered_out = False  # type: ignore[misc]
