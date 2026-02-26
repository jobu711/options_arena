"""Unit tests for market data models: OHLCV, Quote, TickerInfo.

Tests cover:
- Happy path construction with all fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- Decimal precision preserved through construction
- Default values for optional/defaulted fields
- JSON serialization roundtrip
"""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import (
    OHLCV,
    DividendSource,
    MarketCapTier,
    Quote,
    TickerInfo,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv() -> OHLCV:
    """Create a valid OHLCV instance for reuse."""
    return OHLCV(
        ticker="AAPL",
        date=date(2025, 6, 15),
        open=Decimal("185.50"),
        high=Decimal("187.25"),
        low=Decimal("184.00"),
        close=Decimal("186.75"),
        volume=45_000_000,
        adjusted_close=Decimal("186.75"),
    )


@pytest.fixture
def sample_quote() -> Quote:
    """Create a valid Quote instance for reuse."""
    return Quote(
        ticker="AAPL",
        price=Decimal("186.50"),
        bid=Decimal("186.45"),
        ask=Decimal("186.55"),
        volume=12_000_000,
        timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_ticker_info() -> TickerInfo:
    """Create a valid TickerInfo instance with all fields populated."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        market_cap=3_000_000_000_000,
        market_cap_tier=MarketCapTier.MEGA,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        dividend_rate=0.96,
        trailing_dividend_rate=0.92,
        current_price=Decimal("186.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
    )


# ---------------------------------------------------------------------------
# OHLCV Tests
# ---------------------------------------------------------------------------


class TestOHLCV:
    """Tests for the OHLCV model."""

    def test_happy_path_construction(self, sample_ohlcv: OHLCV) -> None:
        """OHLCV constructs with all fields correctly assigned."""
        assert sample_ohlcv.ticker == "AAPL"
        assert sample_ohlcv.date == date(2025, 6, 15)
        assert sample_ohlcv.open == Decimal("185.50")
        assert sample_ohlcv.high == Decimal("187.25")
        assert sample_ohlcv.low == Decimal("184.00")
        assert sample_ohlcv.close == Decimal("186.75")
        assert sample_ohlcv.volume == 45_000_000
        assert sample_ohlcv.adjusted_close == Decimal("186.75")

    def test_frozen_enforcement(self, sample_ohlcv: OHLCV) -> None:
        """OHLCV is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_ohlcv.close = Decimal("999.99")  # type: ignore[misc]

    def test_decimal_precision_preserved(self) -> None:
        """Decimal values preserve exact precision through construction."""
        ohlcv = OHLCV(
            ticker="MSFT",
            date=date(2025, 1, 1),
            open=Decimal("1.05"),
            high=Decimal("1.10"),
            low=Decimal("1.00"),
            close=Decimal("1.05"),
            volume=100,
            adjusted_close=Decimal("1.05"),
        )
        assert ohlcv.open == Decimal("1.05")
        assert str(ohlcv.open) == "1.05"

    def test_json_roundtrip(self, sample_ohlcv: OHLCV) -> None:
        """OHLCV survives JSON serialization/deserialization unchanged."""
        json_str = sample_ohlcv.model_dump_json()
        restored = OHLCV.model_validate_json(json_str)
        assert restored == sample_ohlcv


# ---------------------------------------------------------------------------
# OHLCV Validator Tests
# ---------------------------------------------------------------------------


class TestOHLCVValidators:
    """Tests for OHLCV field and model validators."""

    def test_ohlcv_valid_construction(self) -> None:
        """OHLCV constructs successfully with valid data (positive case)."""
        ohlcv = OHLCV(
            ticker="AAPL",
            date=date(2025, 6, 15),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=45_000_000,
            adjusted_close=Decimal("186.75"),
        )
        assert ohlcv.open == Decimal("185.50")
        assert ohlcv.high == Decimal("187.25")
        assert ohlcv.low == Decimal("184.00")
        assert ohlcv.close == Decimal("186.75")
        assert ohlcv.volume == 45_000_000

    @pytest.mark.parametrize("field", ["open", "high", "low", "close", "adjusted_close"])
    def test_ohlcv_rejects_zero_price(self, field: str) -> None:
        """OHLCV rejects zero for each price field."""
        kwargs = {
            "ticker": "AAPL",
            "date": date(2025, 6, 15),
            "open": Decimal("185.50"),
            "high": Decimal("187.25"),
            "low": Decimal("184.00"),
            "close": Decimal("186.75"),
            "volume": 45_000_000,
            "adjusted_close": Decimal("186.75"),
        }
        kwargs[field] = Decimal("0")
        with pytest.raises(ValidationError, match="price must be finite and > 0"):
            OHLCV(**kwargs)

    @pytest.mark.parametrize("field", ["open", "high", "low", "close", "adjusted_close"])
    def test_ohlcv_rejects_negative_price(self, field: str) -> None:
        """OHLCV rejects negative values for each price field."""
        kwargs = {
            "ticker": "AAPL",
            "date": date(2025, 6, 15),
            "open": Decimal("185.50"),
            "high": Decimal("187.25"),
            "low": Decimal("184.00"),
            "close": Decimal("186.75"),
            "volume": 45_000_000,
            "adjusted_close": Decimal("186.75"),
        }
        kwargs[field] = Decimal("-10.00")
        with pytest.raises(ValidationError, match="price must be finite and > 0"):
            OHLCV(**kwargs)

    @pytest.mark.parametrize("field", ["open", "high", "low", "close", "adjusted_close"])
    def test_ohlcv_rejects_nan_price(self, field: str) -> None:
        """OHLCV rejects Decimal('NaN') for each price field.

        Pydantic's core validation may reject NaN before the field_validator runs,
        so we match either our custom message or Pydantic's built-in 'finite_number' error.
        """
        kwargs = {
            "ticker": "AAPL",
            "date": date(2025, 6, 15),
            "open": Decimal("185.50"),
            "high": Decimal("187.25"),
            "low": Decimal("184.00"),
            "close": Decimal("186.75"),
            "volume": 45_000_000,
            "adjusted_close": Decimal("186.75"),
        }
        kwargs[field] = Decimal("NaN")
        with pytest.raises(ValidationError, match="finite"):
            OHLCV(**kwargs)

    @pytest.mark.parametrize("field", ["open", "high", "low", "close", "adjusted_close"])
    def test_ohlcv_rejects_inf_price(self, field: str) -> None:
        """OHLCV rejects Decimal('Inf') for each price field.

        Pydantic's core validation may reject Inf before the field_validator runs,
        so we match either our custom message or Pydantic's built-in 'finite_number' error.
        """
        kwargs = {
            "ticker": "AAPL",
            "date": date(2025, 6, 15),
            "open": Decimal("185.50"),
            "high": Decimal("187.25"),
            "low": Decimal("184.00"),
            "close": Decimal("186.75"),
            "volume": 45_000_000,
            "adjusted_close": Decimal("186.75"),
        }
        kwargs[field] = Decimal("Inf")
        with pytest.raises(ValidationError, match="finite"):
            OHLCV(**kwargs)

    def test_ohlcv_rejects_negative_volume(self) -> None:
        """OHLCV rejects negative volume."""
        with pytest.raises(ValidationError, match="volume must be >= 0"):
            OHLCV(
                ticker="AAPL",
                date=date(2025, 6, 15),
                open=Decimal("185.50"),
                high=Decimal("187.25"),
                low=Decimal("184.00"),
                close=Decimal("186.75"),
                volume=-1,
                adjusted_close=Decimal("186.75"),
            )

    def test_ohlcv_allows_zero_volume(self) -> None:
        """OHLCV accepts volume = 0 (valid for non-trading days)."""
        ohlcv = OHLCV(
            ticker="AAPL",
            date=date(2025, 6, 15),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=0,
            adjusted_close=Decimal("186.75"),
        )
        assert ohlcv.volume == 0

    def test_ohlcv_rejects_high_less_than_low(self) -> None:
        """OHLCV rejects candle where high < low."""
        with pytest.raises(ValidationError, match=r"high .* must be >= low"):
            OHLCV(
                ticker="AAPL",
                date=date(2025, 6, 15),
                open=Decimal("183.00"),
                high=Decimal("183.00"),
                low=Decimal("185.00"),
                close=Decimal("183.00"),
                volume=45_000_000,
                adjusted_close=Decimal("183.00"),
            )

    def test_ohlcv_rejects_open_outside_range(self) -> None:
        """OHLCV rejects open price outside [low, high] range."""
        with pytest.raises(ValidationError, match=r"open .* must be in"):
            OHLCV(
                ticker="AAPL",
                date=date(2025, 6, 15),
                open=Decimal("190.00"),  # above high
                high=Decimal("187.25"),
                low=Decimal("184.00"),
                close=Decimal("186.75"),
                volume=45_000_000,
                adjusted_close=Decimal("186.75"),
            )

    def test_ohlcv_rejects_close_outside_range(self) -> None:
        """OHLCV rejects close price outside [low, high] range."""
        with pytest.raises(ValidationError, match=r"close .* must be in"):
            OHLCV(
                ticker="AAPL",
                date=date(2025, 6, 15),
                open=Decimal("185.50"),
                high=Decimal("187.25"),
                low=Decimal("184.00"),
                close=Decimal("183.00"),  # below low
                volume=45_000_000,
                adjusted_close=Decimal("186.75"),
            )

    def test_ohlcv_allows_adjusted_close_outside_range(self) -> None:
        """OHLCV allows adjusted_close outside [low, high] range (splits/dividends)."""
        ohlcv = OHLCV(
            ticker="AAPL",
            date=date(2025, 6, 15),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=45_000_000,
            adjusted_close=Decimal("93.375"),  # half due to 2:1 split
        )
        assert ohlcv.adjusted_close == Decimal("93.375")


# ---------------------------------------------------------------------------
# Quote Tests
# ---------------------------------------------------------------------------


class TestQuote:
    """Tests for the Quote model."""

    def test_happy_path_construction(self, sample_quote: Quote) -> None:
        """Quote constructs with all fields correctly assigned."""
        assert sample_quote.ticker == "AAPL"
        assert sample_quote.price == Decimal("186.50")
        assert sample_quote.bid == Decimal("186.45")
        assert sample_quote.ask == Decimal("186.55")
        assert sample_quote.volume == 12_000_000

    def test_frozen_enforcement(self, sample_quote: Quote) -> None:
        """Quote is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_quote.price = Decimal("999.99")  # type: ignore[misc]

    def test_timestamp_with_utc(self, sample_quote: Quote) -> None:
        """Quote timestamp includes UTC timezone info."""
        assert sample_quote.timestamp.tzinfo is not None
        assert sample_quote.timestamp.tzinfo == UTC

    def test_timestamp_value(self, sample_quote: Quote) -> None:
        """Quote timestamp has the exact value that was provided."""
        expected = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        assert sample_quote.timestamp == expected

    def test_naive_timestamp_raises(self) -> None:
        """Quote rejects naive datetime for timestamp."""
        with pytest.raises(ValidationError, match="UTC"):
            Quote(
                ticker="AAPL",
                price=Decimal("186.50"),
                bid=Decimal("186.45"),
                ask=Decimal("186.55"),
                volume=12_000_000,
                timestamp=datetime(2025, 6, 15, 14, 30, 0),  # naive
            )

    def test_non_utc_timestamp_raises(self) -> None:
        """Quote rejects non-UTC timezone for timestamp."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            Quote(
                ticker="AAPL",
                price=Decimal("186.50"),
                bid=Decimal("186.45"),
                ask=Decimal("186.55"),
                volume=12_000_000,
                timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=est),
            )

    def test_json_roundtrip(self, sample_quote: Quote) -> None:
        """Quote survives JSON serialization/deserialization unchanged."""
        json_str = sample_quote.model_dump_json()
        restored = Quote.model_validate_json(json_str)
        assert restored == sample_quote


# ---------------------------------------------------------------------------
# TickerInfo Tests
# ---------------------------------------------------------------------------


class TestTickerInfo:
    """Tests for the TickerInfo model."""

    def test_happy_path_all_fields(self, sample_ticker_info: TickerInfo) -> None:
        """TickerInfo constructs with all fields correctly assigned."""
        assert sample_ticker_info.ticker == "AAPL"
        assert sample_ticker_info.company_name == "Apple Inc."
        assert sample_ticker_info.sector == "Technology"
        assert sample_ticker_info.market_cap == 3_000_000_000_000
        assert sample_ticker_info.market_cap_tier == MarketCapTier.MEGA
        assert sample_ticker_info.dividend_yield == pytest.approx(0.005)
        assert sample_ticker_info.dividend_source == DividendSource.FORWARD
        assert sample_ticker_info.dividend_rate == pytest.approx(0.96)
        assert sample_ticker_info.trailing_dividend_rate == pytest.approx(0.92)
        assert sample_ticker_info.current_price == Decimal("186.50")
        assert sample_ticker_info.fifty_two_week_high == Decimal("199.62")
        assert sample_ticker_info.fifty_two_week_low == Decimal("164.08")

    def test_dividend_yield_defaults_to_zero(self) -> None:
        """TickerInfo dividend_yield defaults to 0.0 when not provided."""
        info = TickerInfo(
            ticker="TSLA",
            company_name="Tesla Inc.",
            sector="Automotive",
            current_price=Decimal("250.00"),
            fifty_two_week_high=Decimal("300.00"),
            fifty_two_week_low=Decimal("150.00"),
        )
        assert info.dividend_yield == pytest.approx(0.0)

    def test_dividend_source_defaults_to_none(self) -> None:
        """TickerInfo dividend_source defaults to DividendSource.NONE when not provided."""
        info = TickerInfo(
            ticker="TSLA",
            company_name="Tesla Inc.",
            sector="Automotive",
            current_price=Decimal("250.00"),
            fifty_two_week_high=Decimal("300.00"),
            fifty_two_week_low=Decimal("150.00"),
        )
        assert info.dividend_source == DividendSource.NONE

    def test_dividend_rate_accepts_none(self) -> None:
        """TickerInfo dividend_rate defaults to None and accepts None."""
        info = TickerInfo(
            ticker="TSLA",
            company_name="Tesla Inc.",
            sector="Automotive",
            current_price=Decimal("250.00"),
            fifty_two_week_high=Decimal("300.00"),
            fifty_two_week_low=Decimal("150.00"),
            dividend_rate=None,
        )
        assert info.dividend_rate is None

    def test_trailing_dividend_rate_accepts_none(self) -> None:
        """TickerInfo trailing_dividend_rate defaults to None and accepts None."""
        info = TickerInfo(
            ticker="TSLA",
            company_name="Tesla Inc.",
            sector="Automotive",
            current_price=Decimal("250.00"),
            fifty_two_week_high=Decimal("300.00"),
            fifty_two_week_low=Decimal("150.00"),
            trailing_dividend_rate=None,
        )
        assert info.trailing_dividend_rate is None

    def test_market_cap_tier_accepts_none(self) -> None:
        """TickerInfo market_cap_tier defaults to None when not provided."""
        info = TickerInfo(
            ticker="XYZ",
            company_name="Small Corp",
            sector="Industrials",
            current_price=Decimal("10.00"),
            fifty_two_week_high=Decimal("15.00"),
            fifty_two_week_low=Decimal("5.00"),
        )
        assert info.market_cap_tier is None

    def test_market_cap_tier_accepts_large(self) -> None:
        """TickerInfo market_cap_tier accepts MarketCapTier.LARGE."""
        info = TickerInfo(
            ticker="XYZ",
            company_name="Large Corp",
            sector="Industrials",
            market_cap_tier=MarketCapTier.LARGE,
            current_price=Decimal("100.00"),
            fifty_two_week_high=Decimal("150.00"),
            fifty_two_week_low=Decimal("50.00"),
        )
        assert info.market_cap_tier == MarketCapTier.LARGE

    def test_frozen_enforcement(self, sample_ticker_info: TickerInfo) -> None:
        """TickerInfo is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_ticker_info.ticker = "MSFT"  # type: ignore[misc]

    def test_json_roundtrip(self, sample_ticker_info: TickerInfo) -> None:
        """TickerInfo survives JSON serialization/deserialization unchanged."""
        json_str = sample_ticker_info.model_dump_json()
        restored = TickerInfo.model_validate_json(json_str)
        assert restored == sample_ticker_info
