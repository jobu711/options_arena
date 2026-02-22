"""Options Arena — Domain exception hierarchy.

All data-fetching and data-quality exceptions inherit from ``DataFetchError``.
No business logic — pure exception definitions only.
"""


class DataFetchError(Exception):
    """Base exception for all data fetching and data quality errors."""


class TickerNotFoundError(DataFetchError):
    """Raised when a requested ticker symbol cannot be found in any data source."""


class InsufficientDataError(DataFetchError):
    """Raised when available data is insufficient for the requested computation."""


class DataSourceUnavailableError(DataFetchError):
    """Raised when an external data source is unreachable or returns an error."""


class RateLimitExceededError(DataFetchError):
    """Raised when an external API rate limit has been exceeded."""
