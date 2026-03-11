"""Tests for CLI scan command filter argument mapping to ScanFilterSpec.

Covers:
  - --sector args map to UniverseFilters.sectors
  - --top-n maps to OptionsFilters.top_n
  - --min-score maps to ScoringFilters.min_score
  - --min-confidence maps to ScoringFilters.min_direction_confidence
  - --market-cap maps to UniverseFilters.market_cap_tiers
  - --min-dte / --max-dte map to OptionsFilters
  - --direction maps to ScoringFilters.direction_filter
  - --exclude-earnings maps to OptionsFilters.exclude_near_earnings_days
  - --min-price / --max-price map to UniverseFilters
  - Default args produce default ScanFilterSpec
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from options_arena.models.enums import (
    GICSSector,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_scan_async_call(
    cli_args: list[str],
) -> dict[str, object]:
    """Invoke the CLI scan command and capture the args passed to _scan_async.

    Returns the keyword arguments dictionary from the _scan_async call.
    """
    from typer.testing import CliRunner

    from options_arena.cli import app

    captured: dict[str, object] = {}

    async def _fake_scan_async(*args: object, **kwargs: object) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    runner = CliRunner()
    with patch("options_arena.cli.commands._scan_async", _fake_scan_async):
        result = runner.invoke(app, ["scan", *cli_args])

    if result.exit_code != 0 and "args" not in captured:
        raise AssertionError(f"CLI failed (exit={result.exit_code}): {result.output}")

    return captured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCLIFilterArgs:
    """CLI scan argument → _scan_async parameter mapping tests."""

    def test_default_args(self) -> None:
        """Verify default scan command produces expected defaults."""
        captured = _capture_scan_async_call([])
        args = captured["args"]
        # First positional arg is preset (default SP500)
        assert args[0] == ScanPreset.SP500
        # top_n default = 50
        assert args[1] == 50
        # min_score default = None (unset unless explicitly provided)
        assert args[2] is None

    def test_sector_args(self) -> None:
        """Verify --sector args are parsed and passed as GICSSector list."""
        captured = _capture_scan_async_call(["--sector", "technology", "--sector", "healthcare"])
        args = captured["args"]
        sectors = args[3]  # 4th positional arg
        assert GICSSector.INFORMATION_TECHNOLOGY in sectors
        assert GICSSector.HEALTH_CARE in sectors

    def test_top_n_arg(self) -> None:
        """Verify --top-n maps through to _scan_async."""
        captured = _capture_scan_async_call(["--top-n", "30"])
        args = captured["args"]
        assert args[1] == 30

    def test_min_score_arg(self) -> None:
        """Verify --min-score maps through to _scan_async."""
        captured = _capture_scan_async_call(["--min-score", "40.0"])
        args = captured["args"]
        assert args[2] == pytest.approx(40.0)

    def test_min_confidence_arg(self) -> None:
        """Verify --min-confidence maps through to _scan_async."""
        captured = _capture_scan_async_call(["--min-confidence", "0.5"])
        kwargs = captured["kwargs"]
        assert kwargs["min_confidence"] == pytest.approx(0.5)

    def test_market_cap_arg(self) -> None:
        """Verify --market-cap args are parsed as MarketCapTier list."""
        captured = _capture_scan_async_call(["--market-cap", "mega", "--market-cap", "large"])
        args = captured["args"]
        cap_tiers = args[4]  # 5th positional arg
        assert MarketCapTier.MEGA in cap_tiers
        assert MarketCapTier.LARGE in cap_tiers

    def test_direction_arg(self) -> None:
        """Verify --direction maps through to _scan_async."""
        captured = _capture_scan_async_call(["--direction", "bullish"])
        args = captured["args"]
        assert args[6] == SignalDirection.BULLISH

    def test_exclude_earnings_arg(self) -> None:
        """Verify --exclude-earnings maps through to _scan_async."""
        captured = _capture_scan_async_call(["--exclude-earnings", "7"])
        args = captured["args"]
        assert args[5] == 7

    def test_min_max_dte_args(self) -> None:
        """Verify --min-dte and --max-dte map through to _scan_async."""
        captured = _capture_scan_async_call(["--min-dte", "30", "--max-dte", "90"])
        kwargs = captured["kwargs"]
        assert kwargs["min_dte"] == 30
        assert kwargs["max_dte"] == 90

    def test_min_max_price_args(self) -> None:
        """Verify --min-price and --max-price map through to _scan_async."""
        captured = _capture_scan_async_call(["--min-price", "20.0", "--max-price", "500.0"])
        kwargs = captured["kwargs"]
        assert kwargs["min_price"] == pytest.approx(20.0)
        assert kwargs["max_price"] == pytest.approx(500.0)

    def test_custom_tickers_arg(self) -> None:
        """Verify --tickers parses comma-separated tickers."""
        captured = _capture_scan_async_call(["--tickers", "AAPL,MSFT,GOOG"])
        kwargs = captured["kwargs"]
        custom = kwargs["custom_tickers"]
        assert custom == ["AAPL", "MSFT", "GOOG"]
