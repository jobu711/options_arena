"""Tests for OutcomeCollector service.

Covers:
  - Stock return computation from entry/exit prices.
  - Contract return computation from mid prices.
  - Intrinsic value for calls (ITM and OTM).
  - Intrinsic value for puts (ITM and OTM).
  - Expired worthless contract returns -100%.
  - Expired ITM contract uses intrinsic value.
  - Never raises on fetch_quote failure.
  - Partial results on mixed success/failure.
  - is_winner True for positive return.
  - is_winner False for negative return.
  - Collect all configured periods when holding_days is None.
  - DTE at exit computed correctly.
  - get_summary aggregation.
  - Market-timezone-aware date via _market_today().
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from options_arena.models.analytics import PerformanceSummary, RecommendedContract
from options_arena.models.config import AnalyticsConfig
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    OutcomeCollectionMethod,
    SignalDirection,
)
from options_arena.models.market_data import Quote
from options_arena.services.outcome_collector import OutcomeCollector, _market_today

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_contract(
    *,
    contract_id: int = 1,
    ticker: str = "AAPL",
    option_type: OptionType = OptionType.CALL,
    strike: Decimal = Decimal("185.00"),
    expiration: date = date(2026, 4, 15),
    entry_stock_price: Decimal | None = Decimal("180.00"),
    entry_mid: Decimal = Decimal("5.00"),
    direction: SignalDirection = SignalDirection.BULLISH,
    **overrides: object,
) -> RecommendedContract:
    """Build a RecommendedContract with sensible defaults for testing."""
    defaults: dict[str, object] = {
        "id": contract_id,
        "scan_run_id": 1,
        "ticker": ticker,
        "option_type": option_type,
        "strike": strike,
        "expiration": expiration,
        "bid": Decimal("4.80"),
        "ask": Decimal("5.20"),
        "last": Decimal("5.00"),
        "volume": 1000,
        "open_interest": 5000,
        "market_iv": 0.30,
        "exercise_style": ExerciseStyle.AMERICAN,
        "entry_stock_price": entry_stock_price,
        "entry_mid": entry_mid,
        "direction": direction,
        "composite_score": 75.0,
        "risk_free_rate": 0.045,
        "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RecommendedContract(**defaults)  # type: ignore[arg-type]


def make_quote(ticker: str = "AAPL", price: Decimal = Decimal("190.00")) -> Quote:
    """Build a Quote for testing."""
    return Quote(
        ticker=ticker,
        price=price,
        bid=price - Decimal("0.10"),
        ask=price + Decimal("0.10"),
        volume=1_000_000,
        timestamp=datetime(2026, 3, 10, 15, 0, 0, tzinfo=UTC),
    )


def make_collector(
    holding_periods: list[int] | None = None,
    contracts_needing: list[RecommendedContract] | None = None,
    quote: Quote | None = None,
    quote_side_effect: Exception | None = None,
) -> OutcomeCollector:
    """Build an OutcomeCollector with mocked dependencies."""
    config = AnalyticsConfig(holding_periods=holding_periods or [1, 5, 10, 20])

    repo = AsyncMock()
    repo.get_contracts_needing_outcomes = AsyncMock(return_value=contracts_needing or [])
    repo.save_contract_outcomes = AsyncMock()
    repo.get_performance_summary = AsyncMock()

    market_data = AsyncMock()
    if quote_side_effect is not None:
        market_data.fetch_quote = AsyncMock(side_effect=quote_side_effect)
    else:
        market_data.fetch_quote = AsyncMock(return_value=quote or make_quote())

    return OutcomeCollector(config, repo, market_data)


# ---------------------------------------------------------------------------
# Stock return computation
# ---------------------------------------------------------------------------


class TestStockReturnComputation:
    """Tests for _compute_stock_return."""

    def test_positive_return(self) -> None:
        """Verify (exit - entry) / entry * 100 for positive stock return."""
        collector = make_collector()
        result = collector._compute_stock_return(Decimal("100.00"), Decimal("110.00"))
        assert result == pytest.approx(10.0)

    def test_negative_return(self) -> None:
        """Verify negative stock return computation."""
        collector = make_collector()
        result = collector._compute_stock_return(Decimal("100.00"), Decimal("90.00"))
        assert result == pytest.approx(-10.0)

    def test_zero_entry_price_returns_none(self) -> None:
        """Verify zero entry price guards against division by zero."""
        collector = make_collector()
        result = collector._compute_stock_return(Decimal("0"), Decimal("100.00"))
        assert result is None

    def test_none_entry_price_returns_none(self) -> None:
        """Verify None entry price returns None (unavailable data)."""
        collector = make_collector()
        result = collector._compute_stock_return(None, Decimal("100.00"))
        assert result is None


# ---------------------------------------------------------------------------
# Contract return computation
# ---------------------------------------------------------------------------


class TestContractReturnComputation:
    """Tests for _compute_contract_return."""

    def test_positive_contract_return(self) -> None:
        """Verify (exit_mid - entry_mid) / entry_mid * 100."""
        collector = make_collector()
        result = collector._compute_contract_return(Decimal("5.00"), Decimal("7.50"))
        assert result == pytest.approx(50.0)

    def test_negative_contract_return(self) -> None:
        """Verify negative contract return."""
        collector = make_collector()
        result = collector._compute_contract_return(Decimal("5.00"), Decimal("2.50"))
        assert result == pytest.approx(-50.0)

    def test_zero_entry_mid_returns_none(self) -> None:
        """Verify zero entry_mid returns None (invalid data guard)."""
        collector = make_collector()
        result = collector._compute_contract_return(Decimal("0"), Decimal("5.00"))
        assert result is None


# ---------------------------------------------------------------------------
# Intrinsic value computation
# ---------------------------------------------------------------------------


class TestIntrinsicValue:
    """Tests for _compute_intrinsic_value."""

    def test_call_itm(self) -> None:
        """Verify max(0, S-K) for in-the-money call."""
        collector = make_collector()
        result = collector._compute_intrinsic_value(
            OptionType.CALL, Decimal("185.00"), Decimal("190.00")
        )
        assert result == Decimal("5.00")

    def test_call_otm(self) -> None:
        """Verify max(0, S-K) = 0 for out-of-the-money call."""
        collector = make_collector()
        result = collector._compute_intrinsic_value(
            OptionType.CALL, Decimal("185.00"), Decimal("180.00")
        )
        assert result == Decimal("0")

    def test_put_itm(self) -> None:
        """Verify max(0, K-S) for in-the-money put."""
        collector = make_collector()
        result = collector._compute_intrinsic_value(
            OptionType.PUT, Decimal("185.00"), Decimal("180.00")
        )
        assert result == Decimal("5.00")

    def test_put_otm(self) -> None:
        """Verify max(0, K-S) = 0 for out-of-the-money put."""
        collector = make_collector()
        result = collector._compute_intrinsic_value(
            OptionType.PUT, Decimal("185.00"), Decimal("190.00")
        )
        assert result == Decimal("0")


# ---------------------------------------------------------------------------
# Expired contract handling
# ---------------------------------------------------------------------------


class TestExpiredContracts:
    """Tests for expired contract processing."""

    @pytest.mark.asyncio
    async def test_expired_worthless_returns_minus_100(self) -> None:
        """Verify expired OTM contract returns -100%."""
        # Call with strike=185, stock=180 -> OTM -> worthless
        contract = make_contract(
            strike=Decimal("185.00"),
            option_type=OptionType.CALL,
            expiration=date(2026, 3, 1),  # Already expired
        )
        collector = make_collector(
            contracts_needing=[contract],
            quote=make_quote(price=Decimal("180.00")),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert len(outcomes) == 1
        assert outcomes[0].contract_return_pct == pytest.approx(-100.0)
        assert outcomes[0].collection_method is OutcomeCollectionMethod.EXPIRED_WORTHLESS
        assert outcomes[0].is_winner is False

    @pytest.mark.asyncio
    async def test_expired_itm_uses_intrinsic(self) -> None:
        """Verify expired ITM contract uses intrinsic value for return calc."""
        # Call with strike=185, stock=195 -> ITM, intrinsic=10
        # Entry mid=5.00, so return = (10-5)/5*100 = 100%
        contract = make_contract(
            strike=Decimal("185.00"),
            option_type=OptionType.CALL,
            entry_mid=Decimal("5.00"),
            expiration=date(2026, 3, 1),
        )
        collector = make_collector(
            contracts_needing=[contract],
            quote=make_quote(price=Decimal("195.00")),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert len(outcomes) == 1
        assert outcomes[0].contract_return_pct == pytest.approx(100.0)
        assert outcomes[0].collection_method is OutcomeCollectionMethod.INTRINSIC
        assert outcomes[0].is_winner is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for never-raises behavior."""

    @pytest.mark.asyncio
    async def test_never_raises_on_fetch_error(self) -> None:
        """Verify collector logs and skips on fetch_quote failure."""
        contract = make_contract(expiration=date(2026, 3, 1))
        collector = make_collector(
            contracts_needing=[contract],
            quote_side_effect=Exception("Network error"),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            # Should NOT raise — returns empty list
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert outcomes == []

    @pytest.mark.asyncio
    async def test_partial_results_on_mixed_success(self) -> None:
        """Verify collector returns successful outcomes even when some fail."""
        good_contract = make_contract(
            contract_id=1,
            ticker="AAPL",
            expiration=date(2026, 3, 1),
            strike=Decimal("185.00"),
        )
        bad_contract = make_contract(
            contract_id=2,
            ticker="BAD",
            expiration=date(2026, 3, 1),
            strike=Decimal("100.00"),
        )

        config = AnalyticsConfig(holding_periods=[10])
        repo = AsyncMock()
        repo.get_contracts_needing_outcomes = AsyncMock(return_value=[good_contract, bad_contract])
        repo.save_contract_outcomes = AsyncMock()

        # First call succeeds (AAPL), second fails (BAD)
        call_count = 0

        async def mock_fetch_quote(ticker: str) -> Quote:
            nonlocal call_count
            call_count += 1
            if ticker == "BAD":
                raise Exception("Ticker not found")
            return make_quote(ticker=ticker, price=Decimal("180.00"))

        market_data = AsyncMock()
        market_data.fetch_quote = mock_fetch_quote

        collector = OutcomeCollector(config, repo, market_data)

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        # Only the successful contract should have an outcome
        assert len(outcomes) == 1


# ---------------------------------------------------------------------------
# Winner flag
# ---------------------------------------------------------------------------


class TestWinnerFlag:
    """Tests for is_winner computation."""

    @pytest.mark.asyncio
    async def test_is_winner_true_for_positive_return(self) -> None:
        """Verify is_winner=True when contract_return_pct > 0."""
        # Expired ITM: strike=185, stock=195, intrinsic=10, entry_mid=5 -> +100%
        contract = make_contract(
            strike=Decimal("185.00"),
            entry_mid=Decimal("5.00"),
            expiration=date(2026, 3, 1),
        )
        collector = make_collector(
            contracts_needing=[contract],
            quote=make_quote(price=Decimal("195.00")),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert len(outcomes) == 1
        assert outcomes[0].is_winner is True

    @pytest.mark.asyncio
    async def test_is_winner_false_for_negative_return(self) -> None:
        """Verify is_winner=False when contract_return_pct <= 0."""
        # Expired ITM but losing: strike=185, stock=186, intrinsic=1, entry_mid=5 -> -80%
        contract = make_contract(
            strike=Decimal("185.00"),
            entry_mid=Decimal("5.00"),
            expiration=date(2026, 3, 1),
        )
        collector = make_collector(
            contracts_needing=[contract],
            quote=make_quote(price=Decimal("186.00")),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert len(outcomes) == 1
        assert outcomes[0].is_winner is False


# ---------------------------------------------------------------------------
# All periods collection
# ---------------------------------------------------------------------------


class TestAllPeriodsCollection:
    """Tests for iterating all configured holding periods."""

    @pytest.mark.asyncio
    async def test_collect_all_periods(self) -> None:
        """Verify None holding_days iterates all configured periods."""
        config = AnalyticsConfig(holding_periods=[1, 5])
        repo = AsyncMock()
        repo.get_contracts_needing_outcomes = AsyncMock(return_value=[])
        repo.save_contract_outcomes = AsyncMock()
        market_data = AsyncMock()

        collector = OutcomeCollector(config, repo, market_data)
        await collector.collect_outcomes(holding_days=None)

        # Should have been called twice (once for each period)
        assert repo.get_contracts_needing_outcomes.call_count == 2


# ---------------------------------------------------------------------------
# DTE at exit
# ---------------------------------------------------------------------------


class TestDTEAtExit:
    """Tests for DTE at exit computation."""

    @pytest.mark.asyncio
    async def test_dte_at_exit_computed(self) -> None:
        """Verify DTE at exit = (expiration - exit_date).days."""
        # Expiration: 2026-04-15, exit date (today): 2026-03-10
        # DTE at exit = (2026-04-15 - 2026-03-10).days = 36
        contract = make_contract(
            expiration=date(2026, 4, 15),  # Still active
        )
        collector = make_collector(
            contracts_needing=[contract],
            quote=make_quote(price=Decimal("190.00")),
        )

        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            outcomes = await collector.collect_outcomes(holding_days=10)

        assert len(outcomes) == 1
        expected_dte = (date(2026, 4, 15) - date(2026, 3, 10)).days
        assert outcomes[0].dte_at_exit == expected_dte


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    """Tests for get_summary delegation to repository."""

    @pytest.mark.asyncio
    async def test_get_summary_delegates_to_repo(self) -> None:
        """Verify get_summary delegates to Repository.get_performance_summary."""
        config = AnalyticsConfig()
        repo = AsyncMock()

        empty_summary = PerformanceSummary(
            lookback_days=30,
            total_contracts=0,
            total_with_outcomes=0,
        )
        repo.get_performance_summary = AsyncMock(return_value=empty_summary)

        market_data = AsyncMock()
        collector = OutcomeCollector(config, repo, market_data)

        summary = await collector.get_summary(lookback_days=30)

        repo.get_performance_summary.assert_called_once_with(30)
        assert isinstance(summary, PerformanceSummary)
        assert summary.total_contracts == 0
        assert summary.total_with_outcomes == 0
        assert summary.overall_win_rate is None


# ---------------------------------------------------------------------------
# Market-timezone-aware dates
# ---------------------------------------------------------------------------


class TestMarketToday:
    """Tests for _market_today() helper returning Eastern timezone date."""

    def test_market_today_returns_eastern_date(self) -> None:
        """Verify _market_today() returns date in Eastern timezone.

        When UTC is 2026-03-11 14:00 (10:00 AM ET), both UTC and Eastern
        agree on the date (March 11). Verify the helper returns that date.
        """
        # 2026-03-11 14:00 UTC = 2026-03-11 10:00 AM EDT (same calendar day)
        mock_now = datetime(2026, 3, 11, 14, 0, 0, tzinfo=UTC)

        with patch(
            "options_arena.services.outcome_collector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = mock_now.astimezone(ZoneInfo("America/New_York"))
            result = _market_today()

        assert result == date(2026, 3, 11)

    def test_market_today_at_utc_midnight_returns_previous_eastern_date(self) -> None:
        """Verify that UTC midnight (7/8 PM Eastern) returns the previous day.

        At 2026-03-11 03:00 UTC it is still 2026-03-10 23:00 EDT.
        _market_today() should return March 10 (previous day), not March 11.
        """
        # 2026-03-11 03:00 UTC = 2026-03-10 23:00 EDT (previous calendar day)
        mock_now = datetime(2026, 3, 11, 3, 0, 0, tzinfo=UTC)

        with patch(
            "options_arena.services.outcome_collector.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = mock_now.astimezone(ZoneInfo("America/New_York"))
            result = _market_today()

        assert result == date(2026, 3, 10)

    @pytest.mark.asyncio
    async def test_expired_check_uses_market_date(self) -> None:
        """Verify contract expiry checking uses Eastern date, not system date.

        Contract expires 2026-03-10. At UTC 2026-03-11 03:00 (ET 2026-03-10 23:00),
        the contract should NOT be considered expired because the market date
        is still March 10 (same as expiration).
        """
        contract = make_contract(
            expiration=date(2026, 3, 10),
        )
        collector = make_collector()

        # Mock _market_today to return March 10 (same as expiration)
        # At UTC midnight on March 11, Eastern is still March 10
        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 10),
        ):
            is_expired = collector._is_expired(contract.expiration)

        # Expiration == today -> NOT expired (< not <=)
        assert is_expired is False

        # Now mock _market_today to return March 11 (day after expiration)
        with patch(
            "options_arena.services.outcome_collector._market_today",
            return_value=date(2026, 3, 11),
        ):
            is_expired = collector._is_expired(contract.expiration)

        # Expiration < today -> expired
        assert is_expired is True
