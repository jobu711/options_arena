"""Tests for exception hierarchy (AUDIT-029).

Verifies that all domain exceptions form the expected inheritance tree:

    Exception
      -> DataFetchError
           -> TickerNotFoundError
           -> InsufficientDataError
           -> DataSourceUnavailableError
           -> RateLimitExceededError

Also tests isinstance behavior, message preservation, and catch-all patterns.
"""

import pytest

from options_arena.utils.exceptions import (
    DataFetchError,
    DataSourceUnavailableError,
    InsufficientDataError,
    RateLimitExceededError,
    TickerNotFoundError,
)

# --------------------------------------------------------------------------- #
# Subclass hierarchy checks
# --------------------------------------------------------------------------- #


@pytest.mark.critical
def test_data_fetch_error_is_exception() -> None:
    assert issubclass(DataFetchError, Exception)


def test_ticker_not_found_is_data_fetch_error() -> None:
    assert issubclass(TickerNotFoundError, DataFetchError)


def test_insufficient_data_is_data_fetch_error() -> None:
    assert issubclass(InsufficientDataError, DataFetchError)


def test_data_source_unavailable_is_data_fetch_error() -> None:
    assert issubclass(DataSourceUnavailableError, DataFetchError)


def test_rate_limit_exceeded_is_data_fetch_error() -> None:
    assert issubclass(RateLimitExceededError, DataFetchError)


# --------------------------------------------------------------------------- #
# isinstance checks (runtime behavior)
# --------------------------------------------------------------------------- #


def test_ticker_not_found_isinstance_of_data_fetch_error() -> None:
    err = TickerNotFoundError("AAPL")
    assert isinstance(err, DataFetchError)
    assert isinstance(err, Exception)


def test_insufficient_data_isinstance_of_data_fetch_error() -> None:
    err = InsufficientDataError("need 200 bars")
    assert isinstance(err, DataFetchError)
    assert isinstance(err, Exception)


def test_data_source_unavailable_isinstance_of_data_fetch_error() -> None:
    err = DataSourceUnavailableError("yfinance down")
    assert isinstance(err, DataFetchError)
    assert isinstance(err, Exception)


def test_rate_limit_exceeded_isinstance_of_data_fetch_error() -> None:
    err = RateLimitExceededError("429")
    assert isinstance(err, DataFetchError)
    assert isinstance(err, Exception)


# --------------------------------------------------------------------------- #
# Message preservation
# --------------------------------------------------------------------------- #


def test_message_preserved_via_str() -> None:
    msg = "AAPL: ticker not found in yfinance"
    err = TickerNotFoundError(msg)
    assert str(err) == msg


def test_message_preserved_via_args() -> None:
    msg = "insufficient data for computation"
    err = InsufficientDataError(msg)
    assert err.args[0] == msg


# --------------------------------------------------------------------------- #
# Catch-all pattern: except DataFetchError catches all subtypes
# --------------------------------------------------------------------------- #


def test_catch_all_catches_all_subtypes() -> None:
    exceptions = [
        TickerNotFoundError("a"),
        InsufficientDataError("b"),
        DataSourceUnavailableError("c"),
        RateLimitExceededError("d"),
    ]
    for exc in exceptions:
        caught = False
        try:
            raise exc
        except DataFetchError:
            caught = True
        assert caught, f"DataFetchError did not catch {type(exc).__name__}"


# --------------------------------------------------------------------------- #
# Negative: subtypes do NOT catch siblings
# --------------------------------------------------------------------------- #


def test_ticker_not_found_does_not_catch_rate_limit() -> None:
    """Sibling exceptions must not catch each other."""
    with_ticker_handler = False
    try:
        raise RateLimitExceededError("too fast")
    except TickerNotFoundError:
        with_ticker_handler = True
    except DataFetchError:
        pass
    assert not with_ticker_handler
