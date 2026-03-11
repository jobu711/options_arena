"""Tests for UniverseFilters.custom_tickers field (#243).

Originally tested on ScanConfig directly; now validates the same behavior on
UniverseFilters.
"""

from __future__ import annotations

import pytest

from options_arena.models.filters import OptionsFilters, ScanFilterSpec, UniverseFilters


class TestScanConfigCustomTickers:
    """Tests for the custom_tickers field on UniverseFilters."""

    def test_default_empty(self) -> None:
        """UniverseFilters() has empty custom_tickers by default."""
        config = UniverseFilters()
        assert config.custom_tickers == []

    def test_uppercase_normalization(self) -> None:
        """Lowercase tickers are uppercased."""
        config = UniverseFilters(custom_tickers=["aapl", "msft"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_strip_whitespace(self) -> None:
        """Whitespace is stripped."""
        config = UniverseFilters(custom_tickers=[" AAPL ", "  MSFT"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_deduplication(self) -> None:
        """Duplicates removed preserving order."""
        config = UniverseFilters(custom_tickers=["AAPL", "MSFT", "AAPL"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_deduplication_case_insensitive(self) -> None:
        """Dedup works across case variants (both uppercased first)."""
        config = UniverseFilters(custom_tickers=["aapl", "AAPL"])
        assert config.custom_tickers == ["AAPL"]

    def test_invalid_ticker_rejected(self) -> None:
        """Tickers not matching regex raise ValueError."""
        with pytest.raises(ValueError, match="Invalid ticker format"):
            UniverseFilters(custom_tickers=["!!!"])

    def test_empty_string_rejected(self) -> None:
        """Empty string in list is rejected by regex."""
        with pytest.raises(ValueError, match="Invalid ticker format"):
            UniverseFilters(custom_tickers=[""])

    def test_cap_at_200(self) -> None:
        """More than 200 tickers raises ValueError."""
        tickers = [f"T{i:04d}" for i in range(201)]
        with pytest.raises(ValueError, match="exceeds 200 tickers"):
            UniverseFilters(custom_tickers=tickers)

    def test_exactly_200_passes(self) -> None:
        """Exactly 200 tickers passes validation."""
        tickers = [f"T{i:04d}" for i in range(200)]
        config = UniverseFilters(custom_tickers=tickers)
        assert len(config.custom_tickers) == 200

    def test_valid_tickers_pass(self) -> None:
        """Valid tickers like AAPL, BRK.B, SPY, ^VIX pass validation."""
        config = UniverseFilters(custom_tickers=["AAPL", "BRK.B", "SPY", "^VIX"])
        assert config.custom_tickers == ["AAPL", "BRK.B", "SPY", "^VIX"]

    def test_existing_behavior_preserved(self) -> None:
        """Empty custom_tickers does not affect other filter fields."""
        from options_arena.models.config import ScanConfig

        config = ScanConfig(
            filters=ScanFilterSpec(
                options=OptionsFilters(top_n=25),
                universe=UniverseFilters(custom_tickers=[]),
            )
        )
        assert config.filters.options.top_n == 25
        assert config.filters.universe.custom_tickers == []

    def test_non_string_item_rejected(self) -> None:
        """Non-string entries are rejected."""
        with pytest.raises(ValueError, match="must be a string"):
            UniverseFilters(custom_tickers=["AAPL", None])  # type: ignore[list-item]
