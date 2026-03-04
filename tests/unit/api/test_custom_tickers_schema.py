"""Tests for ScanRequest.custom_tickers field (#243)."""

from __future__ import annotations

import pytest

from options_arena.api.schemas import ScanRequest


class TestScanRequestCustomTickers:
    """Tests for the custom_tickers field on ScanRequest."""

    def test_default_empty(self) -> None:
        """ScanRequest() has empty custom_tickers by default."""
        req = ScanRequest()
        assert req.custom_tickers == []

    def test_normalization_and_dedup(self) -> None:
        """Tickers are uppercased, stripped, and deduplicated."""
        req = ScanRequest(custom_tickers=["aapl", " msft ", "AAPL"])
        assert req.custom_tickers == ["AAPL", "MSFT"]

    def test_invalid_format_rejected(self) -> None:
        """Invalid ticker format raises validation error."""
        with pytest.raises(ValueError, match="Invalid ticker format"):
            ScanRequest(custom_tickers=["!!!"])

    def test_valid_tickers_pass(self) -> None:
        """Standard equity and index tickers pass validation."""
        req = ScanRequest(custom_tickers=["AAPL", "BRK.B", "^VIX"])
        assert req.custom_tickers == ["AAPL", "BRK.B", "^VIX"]

    def test_cap_at_200(self) -> None:
        """More than 200 tickers raises ValueError."""
        tickers = [f"T{i:04d}" for i in range(201)]
        with pytest.raises(ValueError, match="exceeds 200 tickers"):
            ScanRequest(custom_tickers=tickers)

    def test_backward_compatible(self) -> None:
        """Omitting custom_tickers preserves full backward compatibility."""
        req = ScanRequest()
        assert req.custom_tickers == []
        assert req.sectors == []
        assert req.market_cap_tiers == []
