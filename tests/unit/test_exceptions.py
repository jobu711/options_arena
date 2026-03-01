"""Unit tests for the domain exception hierarchy in options_arena.utils.exceptions.

Tests:
  - DataFetchError is a subclass of Exception
  - Each specific error inherits from DataFetchError
  - Exception messages are accessible via str(err) and err.args[0]
  - isinstance checks work across the hierarchy
  - A single except DataFetchError catches all subclasses
  - Single-string construction produces clean str() output (not tuple repr)
"""

from options_arena.utils import (
    DataFetchError,
    DataSourceUnavailableError,
    InsufficientDataError,
    RateLimitExceededError,
    TickerNotFoundError,
)


class TestDataFetchErrorBase:
    def test_data_fetch_error_is_subclass_of_exception(self) -> None:
        assert issubclass(DataFetchError, Exception)

    def test_data_fetch_error_message_via_str(self) -> None:
        err = DataFetchError("something went wrong")
        assert str(err) == "something went wrong"

    def test_data_fetch_error_message_via_args(self) -> None:
        err = DataFetchError("something went wrong")
        assert err.args[0] == "something went wrong"


class TestTickerNotFoundError:
    def test_ticker_not_found_is_subclass_of_data_fetch_error(self) -> None:
        assert issubclass(TickerNotFoundError, DataFetchError)

    def test_ticker_not_found_isinstance_check(self) -> None:
        err = TickerNotFoundError("AAPL not found")
        assert isinstance(err, DataFetchError)

    def test_ticker_not_found_message(self) -> None:
        err = TickerNotFoundError("AAPL not found")
        assert str(err) == "AAPL not found"

    def test_ticker_not_found_formatted_message_is_clean(self) -> None:
        """str() on single-string construction produces clean message, not tuple."""
        err = TickerNotFoundError("AAPL: invalid price data: None")
        assert str(err) == "AAPL: invalid price data: None"
        assert "(" not in str(err)  # no tuple wrapping


class TestInsufficientDataError:
    def test_insufficient_data_is_subclass_of_data_fetch_error(self) -> None:
        assert issubclass(InsufficientDataError, DataFetchError)

    def test_insufficient_data_isinstance_check(self) -> None:
        err = InsufficientDataError("need 200 bars, got 50")
        assert isinstance(err, DataFetchError)

    def test_insufficient_data_formatted_message_is_clean(self) -> None:
        """str() on single-string construction produces clean message, not tuple."""
        err = InsufficientDataError("AAPL: no OHLCV data returned by yfinance")
        assert str(err) == "AAPL: no OHLCV data returned by yfinance"
        assert "(" not in str(err)


class TestDataSourceUnavailableError:
    def test_data_source_unavailable_is_subclass_of_data_fetch_error(self) -> None:
        assert issubclass(DataSourceUnavailableError, DataFetchError)

    def test_data_source_unavailable_isinstance_check(self) -> None:
        err = DataSourceUnavailableError("yfinance timeout")
        assert isinstance(err, DataFetchError)

    def test_data_source_unavailable_formatted_message_is_clean(self) -> None:
        """str() on single-string construction produces clean message, not tuple."""
        err = DataSourceUnavailableError("yfinance: timeout after 30s")
        assert str(err) == "yfinance: timeout after 30s"
        assert "(" not in str(err)


class TestRateLimitExceededError:
    def test_rate_limit_exceeded_is_subclass_of_data_fetch_error(self) -> None:
        assert issubclass(RateLimitExceededError, DataFetchError)

    def test_rate_limit_exceeded_isinstance_check(self) -> None:
        err = RateLimitExceededError("429 Too Many Requests")
        assert isinstance(err, DataFetchError)


class TestCatchAllWithDataFetchError:
    def test_except_data_fetch_error_catches_ticker_not_found(self) -> None:
        caught = False
        try:
            raise TickerNotFoundError("AAPL")
        except DataFetchError:
            caught = True
        assert caught is True

    def test_except_data_fetch_error_catches_insufficient_data(self) -> None:
        caught = False
        try:
            raise InsufficientDataError("not enough bars")
        except DataFetchError:
            caught = True
        assert caught is True

    def test_except_data_fetch_error_catches_data_source_unavailable(self) -> None:
        caught = False
        try:
            raise DataSourceUnavailableError("server down")
        except DataFetchError:
            caught = True
        assert caught is True

    def test_except_data_fetch_error_catches_rate_limit_exceeded(self) -> None:
        caught = False
        try:
            raise RateLimitExceededError("too fast")
        except DataFetchError:
            caught = True
        assert caught is True
