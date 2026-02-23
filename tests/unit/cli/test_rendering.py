"""Tests for CLI rendering functions and constants.

Tests verify table structure and row counts -- NOT Rich-rendered text
output, which is terminal-dependent and fragile.
"""

from __future__ import annotations

from datetime import UTC, datetime

from options_arena.cli.rendering import DISCLAIMER, render_health_table
from options_arena.models.health import HealthStatus


def _make_health_status(
    name: str,
    *,
    available: bool = True,
    latency_ms: float | None = 50.0,
    error: str | None = None,
) -> HealthStatus:
    """Create a HealthStatus for testing."""
    return HealthStatus(
        service_name=name,
        available=available,
        latency_ms=latency_ms,
        error=error,
        checked_at=datetime.now(UTC),
    )


def test_render_health_table_columns() -> None:
    """Health table has exactly 4 columns: Service, Status, Latency, Error."""
    statuses = [_make_health_status("yfinance")]
    table = render_health_table(statuses)
    assert len(table.columns) == 4
    column_names = [col.header for col in table.columns]  # type: ignore[union-attr]
    assert column_names == ["Service", "Status", "Latency", "Error"]


def test_render_health_table_mixed_statuses() -> None:
    """Table contains one row per HealthStatus."""
    statuses = [
        _make_health_status("yfinance", available=True),
        _make_health_status("fred", available=False, error="timeout"),
        _make_health_status("ollama", available=True, latency_ms=None),
    ]
    table = render_health_table(statuses)
    assert table.row_count == 3


def test_disclaimer_constant_exists() -> None:
    """DISCLAIMER is a non-empty string."""
    assert isinstance(DISCLAIMER, str)
    assert len(DISCLAIMER) > 0
    assert "financial advice" in DISCLAIMER.lower() or "educational" in DISCLAIMER.lower()
