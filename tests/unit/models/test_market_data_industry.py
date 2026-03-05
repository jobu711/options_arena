"""Unit tests for TickerInfo.industry field.

Tests cover:
- Default value ('Unknown') when industry is not provided
- Explicit value assignment
- Backward compatibility with JSON missing the 'industry' key
- JSON serialization roundtrip preserving industry
"""

from decimal import Decimal

from options_arena.models.market_data import TickerInfo


def _make_ticker_info(**overrides: object) -> TickerInfo:
    """Build a minimal TickerInfo with sensible defaults, applying overrides."""
    kwargs: dict[str, object] = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "current_price": Decimal("185.50"),
        "fifty_two_week_high": Decimal("200.00"),
        "fifty_two_week_low": Decimal("140.00"),
    }
    kwargs.update(overrides)
    return TickerInfo(**kwargs)  # type: ignore[arg-type]


class TestTickerInfoIndustry:
    """Tests for the TickerInfo.industry field."""

    def test_industry_default(self) -> None:
        """Verify industry defaults to 'Unknown' when not provided."""
        info = _make_ticker_info()
        assert info.industry == "Unknown"

    def test_industry_set_explicitly(self) -> None:
        """Verify industry can be set to a specific value."""
        info = _make_ticker_info(industry="Consumer Electronics")
        assert info.industry == "Consumer Electronics"

    def test_backward_compat_missing_industry(self) -> None:
        """Verify JSON without 'industry' field deserializes with default."""
        # Simulate cached JSON from before the field existed
        json_without_industry = (
            '{"ticker":"AAPL","company_name":"Apple Inc.","sector":"Technology",'
            '"market_cap":null,"market_cap_tier":null,'
            '"dividend_yield":0.0,"dividend_source":"none",'
            '"dividend_rate":null,"trailing_dividend_rate":null,'
            '"current_price":"185.50","fifty_two_week_high":"200.00",'
            '"fifty_two_week_low":"140.00"}'
        )
        restored = TickerInfo.model_validate_json(json_without_industry)
        assert restored.industry == "Unknown"

    def test_json_roundtrip_with_industry(self) -> None:
        """Verify model_validate_json preserves industry field."""
        info = _make_ticker_info(industry="Semiconductors")
        json_str = info.model_dump_json()
        restored = TickerInfo.model_validate_json(json_str)
        assert restored.industry == "Semiconductors"
        assert restored == info
