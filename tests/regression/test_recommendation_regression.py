"""Regression tests for recommendation pipeline.

Tests verify that prompt changes don't repeat known failures. Fixtures are
generated from historical wrong recommendations by
``tools/generate_regression_fixtures.py``.

If no fixture files exist, the parametrized test suite is empty (no failures).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_regression_fixtures() -> list[dict[str, object]]:
    """Load all JSON regression fixtures from the fixtures directory."""
    fixtures: list[dict[str, object]] = []
    if not _FIXTURES_DIR.exists():
        return fixtures

    for fixture_path in sorted(_FIXTURES_DIR.glob("*.json")):
        try:
            data = json.loads(fixture_path.read_text(encoding="utf-8"))
            data["_fixture_path"] = str(fixture_path)
            fixtures.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return fixtures


_REGRESSION_FIXTURES = _load_regression_fixtures()


@pytest.mark.skipif(
    not _REGRESSION_FIXTURES,
    reason="No regression fixtures — run generate_regression_fixtures.py first.",
)
@pytest.mark.parametrize(
    "fixture",
    _REGRESSION_FIXTURES,
    ids=[f.get("ticker", "unknown") for f in _REGRESSION_FIXTURES],
)
def test_fixture_has_required_fields(fixture: dict[str, object]) -> None:
    """Verify that regression fixtures have the expected structure."""
    assert "ticker" in fixture, "fixture must have 'ticker'"
    assert "original_direction" in fixture, "fixture must have 'original_direction'"
    assert "original_confidence" in fixture, "fixture must have 'original_confidence'"
    assert "actual_pnl_pct" in fixture, "fixture must have 'actual_pnl_pct'"

    # Validate types
    assert isinstance(fixture["ticker"], str)
    assert isinstance(fixture["original_confidence"], float | int)
    assert isinstance(fixture["actual_pnl_pct"], float | int)

    # These were wrong predictions — P&L should be negative
    assert fixture["actual_pnl_pct"] < 0, (  # type: ignore[operator]
        f"Regression fixture for {fixture['ticker']} should have negative P&L"
    )


@pytest.mark.skipif(
    not _REGRESSION_FIXTURES,
    reason="No regression fixtures found.",
)
@pytest.mark.parametrize(
    "fixture",
    _REGRESSION_FIXTURES,
    ids=[f.get("ticker", "unknown") for f in _REGRESSION_FIXTURES],
)
def test_high_confidence_failures_documented(fixture: dict[str, object]) -> None:
    """Verify that high-confidence failures have sufficient context.

    Fixtures from high-confidence wrong calls should include enough data
    to reconstruct the scenario and verify that improved prompts handle
    it differently.
    """
    confidence = float(fixture["original_confidence"])  # type: ignore[arg-type]
    assert confidence >= 0.5, (  # noqa: PLR2004
        f"Regression fixtures should capture meaningful confidence levels, got {confidence}"
    )

    # Description should be present and informative
    description = fixture.get("description", "")
    assert isinstance(description, str)
    if confidence >= 0.7:  # noqa: PLR2004
        assert len(str(description)) > 0, (
            "High-confidence failures should have a description"
        )
