"""Unit tests for ThemeDefinition, ThemeSnapshot, and THEME_ETF_MAPPING.

Tests:
  - Frozen (immutable) models
  - JSON roundtrip
  - UTC datetime validation
  - THEME_ETF_MAPPING has at least 6 themes
  - ThemeSnapshot ticker_count validation
"""

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import THEME_ETF_MAPPING, ThemeDefinition, ThemeSnapshot

# ---------------------------------------------------------------------------
# ThemeDefinition
# ---------------------------------------------------------------------------


class TestThemeDefinition:
    def test_construction_with_all_fields(self) -> None:
        """Verify ThemeDefinition constructs with all fields."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        td = ThemeDefinition(
            name="AI & Machine Learning",
            description="Companies in AI/ML space",
            source_etfs=["ARKK", "BOTZ", "ROBO"],
            updated_at=ts,
        )
        assert td.name == "AI & Machine Learning"
        assert td.description == "Companies in AI/ML space"
        assert td.source_etfs == ["ARKK", "BOTZ", "ROBO"]
        assert td.updated_at == ts

    def test_updated_at_defaults_to_none(self) -> None:
        """Verify updated_at defaults to None when not provided."""
        td = ThemeDefinition(
            name="Test",
            description="Test theme",
            source_etfs=[],
        )
        assert td.updated_at is None

    def test_frozen_model(self) -> None:
        """Verify ThemeDefinition is immutable."""
        td = ThemeDefinition(
            name="Test",
            description="Test theme",
            source_etfs=["SPY"],
        )
        with pytest.raises(ValidationError):
            td.name = "Changed"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """Verify model_validate_json(m.model_dump_json()) == m."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        td = ThemeDefinition(
            name="Cybersecurity",
            description="Cybersecurity ETF theme",
            source_etfs=["HACK", "BUG", "CIBR"],
            updated_at=ts,
        )
        json_str = td.model_dump_json()
        restored = ThemeDefinition.model_validate_json(json_str)
        assert restored == td

    def test_json_roundtrip_none_updated_at(self) -> None:
        """Verify roundtrip works when updated_at is None."""
        td = ThemeDefinition(
            name="Test",
            description="Test theme",
            source_etfs=[],
        )
        json_str = td.model_dump_json()
        restored = ThemeDefinition.model_validate_json(json_str)
        assert restored == td

    def test_rejects_naive_datetime(self) -> None:
        """Verify naive datetime on updated_at raises ValidationError."""
        with pytest.raises(ValidationError, match="UTC"):
            ThemeDefinition(
                name="Test",
                description="Test",
                source_etfs=[],
                updated_at=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """Verify non-UTC timezone on updated_at raises ValidationError."""
        from datetime import timedelta

        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            ThemeDefinition(
                name="Test",
                description="Test",
                source_etfs=[],
                updated_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=est),
            )


# ---------------------------------------------------------------------------
# ThemeSnapshot
# ---------------------------------------------------------------------------


class TestThemeSnapshot:
    def test_construction_with_all_fields(self) -> None:
        """Verify ThemeSnapshot constructs with all fields."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        snap = ThemeSnapshot(
            name="AI & Machine Learning",
            description="AI theme",
            source_etfs=["ARKK", "BOTZ"],
            tickers=["NVDA", "MSFT", "GOOGL"],
            ticker_count=3,
            updated_at=ts,
        )
        assert snap.name == "AI & Machine Learning"
        assert snap.tickers == ["NVDA", "MSFT", "GOOGL"]
        assert snap.ticker_count == 3
        assert snap.updated_at == ts

    def test_frozen_model(self) -> None:
        """Verify ThemeSnapshot is immutable."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        snap = ThemeSnapshot(
            name="Test",
            description="Test",
            source_etfs=[],
            tickers=["AAPL"],
            ticker_count=1,
            updated_at=ts,
        )
        with pytest.raises(ValidationError):
            snap.name = "Changed"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """Verify model_validate_json(m.model_dump_json()) == m."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        snap = ThemeSnapshot(
            name="EVs",
            description="Electric Vehicles",
            source_etfs=["DRIV", "IDRV"],
            tickers=["TSLA", "NIO", "RIVN"],
            ticker_count=3,
            updated_at=ts,
        )
        json_str = snap.model_dump_json()
        restored = ThemeSnapshot.model_validate_json(json_str)
        assert restored == snap

    def test_rejects_naive_datetime(self) -> None:
        """Verify naive datetime on updated_at raises ValidationError."""
        with pytest.raises(ValidationError, match="UTC"):
            ThemeSnapshot(
                name="Test",
                description="Test",
                source_etfs=[],
                tickers=[],
                ticker_count=0,
                updated_at=datetime(2026, 3, 1, 12, 0, 0),
            )

    def test_rejects_negative_ticker_count(self) -> None:
        """Verify negative ticker_count raises ValidationError."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        with pytest.raises(ValidationError, match="ticker_count"):
            ThemeSnapshot(
                name="Test",
                description="Test",
                source_etfs=[],
                tickers=[],
                ticker_count=-1,
                updated_at=ts,
            )

    def test_zero_ticker_count_allowed(self) -> None:
        """Verify zero ticker_count is valid (empty snapshot)."""
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        snap = ThemeSnapshot(
            name="Test",
            description="Test",
            source_etfs=[],
            tickers=[],
            ticker_count=0,
            updated_at=ts,
        )
        assert snap.ticker_count == 0


# ---------------------------------------------------------------------------
# THEME_ETF_MAPPING
# ---------------------------------------------------------------------------


class TestThemeETFMapping:
    def test_has_at_least_6_themes(self) -> None:
        """Verify THEME_ETF_MAPPING defines at least 6 themes."""
        assert len(THEME_ETF_MAPPING) >= 6

    def test_all_values_are_lists(self) -> None:
        """Verify every value in THEME_ETF_MAPPING is a list of strings."""
        for theme_name, etfs in THEME_ETF_MAPPING.items():
            assert isinstance(etfs, list), f"Theme {theme_name!r} value is not a list"
            for etf in etfs:
                assert isinstance(etf, str), f"ETF {etf!r} in {theme_name!r} is not a string"

    def test_expected_themes_present(self) -> None:
        """Verify the core set of expected themes are defined."""
        expected = {
            "AI & Machine Learning",
            "Cannabis",
            "Electric Vehicles",
            "Clean Energy",
            "Cybersecurity",
            "Popular Options",
        }
        assert expected.issubset(set(THEME_ETF_MAPPING.keys()))

    def test_popular_options_has_empty_etf_list(self) -> None:
        """Popular Options is computed from scan data, not ETF holdings."""
        assert THEME_ETF_MAPPING["Popular Options"] == []

    def test_ai_theme_has_etfs(self) -> None:
        """AI & Machine Learning theme has ETF tickers."""
        etfs = THEME_ETF_MAPPING["AI & Machine Learning"]
        assert len(etfs) > 0
        assert "ARKK" in etfs
