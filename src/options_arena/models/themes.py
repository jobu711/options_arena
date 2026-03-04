"""Thematic filtering models for Options Arena.

Defines theme definitions and snapshots for ETF-based thematic screening.
``ThemeDefinition`` is the static configuration; ``ThemeSnapshot`` is a
point-in-time capture of theme holdings resolved from ETF data.

``THEME_ETF_MAPPING`` provides the default set of themes and their source ETFs.
"""

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class ThemeDefinition(BaseModel):
    """Static definition of a thematic filter.

    Frozen (immutable) -- represents a configured theme, not live data.
    ``source_etfs`` lists ETF tickers whose holdings define the theme.
    ``updated_at`` is ``None`` when the definition has not been refreshed.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    source_etfs: list[str]
    updated_at: datetime | None = None

    @field_validator("updated_at")
    @classmethod
    def validate_utc(cls, v: datetime | None) -> datetime | None:
        """Ensure updated_at is UTC when set."""
        if v is not None and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("updated_at must be UTC")
        return v


class ThemeSnapshot(BaseModel):
    """Point-in-time snapshot of a resolved theme.

    Frozen (immutable) -- represents a captured state of theme holdings.
    ``tickers`` contains the resolved ticker symbols from ETF holdings.
    ``ticker_count`` is the number of unique tickers in the snapshot.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    source_etfs: list[str]
    tickers: list[str]
    ticker_count: int
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure updated_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("updated_at must be UTC")
        return v

    @field_validator("ticker_count")
    @classmethod
    def validate_ticker_count(cls, v: int) -> int:
        """Ensure ticker_count is non-negative."""
        if v < 0:
            raise ValueError(f"ticker_count must be >= 0, got {v}")
        return v


THEME_ETF_MAPPING: dict[str, list[str]] = {
    "AI & Machine Learning": ["ARKK", "BOTZ", "ROBO", "AIQ"],
    "Cannabis": ["MSOS", "MJ", "YOLO"],
    "Electric Vehicles": ["DRIV", "IDRV", "LIT"],
    "Clean Energy": ["ICLN", "TAN", "QCLN"],
    "Cybersecurity": ["HACK", "BUG", "CIBR"],
    "Popular Options": [],  # computed from scan data, not ETF holdings
}
