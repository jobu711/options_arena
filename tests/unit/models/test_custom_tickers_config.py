"""Tests for ScanConfig.custom_tickers field (#243)."""

from __future__ import annotations

import pytest

from options_arena.models.config import ScanConfig


class TestScanConfigCustomTickers:
    """Tests for the custom_tickers field on ScanConfig."""

    def test_default_empty(self) -> None:
        """ScanConfig() has empty custom_tickers by default."""
        config = ScanConfig()
        assert config.custom_tickers == []

    def test_uppercase_normalization(self) -> None:
        """Lowercase tickers are uppercased."""
        config = ScanConfig(custom_tickers=["aapl", "msft"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_strip_whitespace(self) -> None:
        """Whitespace is stripped."""
        config = ScanConfig(custom_tickers=[" AAPL ", "  MSFT"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_deduplication(self) -> None:
        """Duplicates removed preserving order."""
        config = ScanConfig(custom_tickers=["AAPL", "MSFT", "AAPL"])
        assert config.custom_tickers == ["AAPL", "MSFT"]

    def test_deduplication_case_insensitive(self) -> None:
        """Dedup works across case variants (both uppercased first)."""
        config = ScanConfig(custom_tickers=["aapl", "AAPL"])
        assert config.custom_tickers == ["AAPL"]

    def test_invalid_ticker_rejected(self) -> None:
        """Tickers not matching regex raise ValueError."""
        with pytest.raises(ValueError, match="Invalid ticker format"):
            ScanConfig(custom_tickers=["!!!"])

    def test_empty_string_rejected(self) -> None:
        """Empty string in list is rejected by regex."""
        with pytest.raises(ValueError, match="Invalid ticker format"):
            ScanConfig(custom_tickers=[""])

    def test_cap_at_200(self) -> None:
        """More than 200 tickers raises ValueError."""
        tickers = [f"T{i:04d}" for i in range(201)]
        with pytest.raises(ValueError, match="exceeds 200 tickers"):
            ScanConfig(custom_tickers=tickers)

    def test_exactly_200_passes(self) -> None:
        """Exactly 200 tickers passes validation."""
        tickers = [f"T{i:04d}" for i in range(200)]
        config = ScanConfig(custom_tickers=tickers)
        assert len(config.custom_tickers) == 200

    def test_valid_tickers_pass(self) -> None:
        """Valid tickers like AAPL, BRK.B, SPY, ^VIX pass validation."""
        config = ScanConfig(custom_tickers=["AAPL", "BRK.B", "SPY", "^VIX"])
        assert config.custom_tickers == ["AAPL", "BRK.B", "SPY", "^VIX"]

    def test_existing_behavior_preserved(self) -> None:
        """Empty custom_tickers does not affect other config fields."""
        config = ScanConfig(top_n=25, custom_tickers=[])
        assert config.top_n == 25
        assert config.custom_tickers == []

    def test_non_string_item_rejected(self) -> None:
        """Non-string entries are rejected."""
        with pytest.raises(ValueError, match="must be a string"):
            ScanConfig(custom_tickers=["AAPL", None])  # type: ignore[list-item]
