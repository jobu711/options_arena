"""Tests for scan_run_id field on DebateResultDetail schema (#307)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from options_arena.api.schemas import DebateResultDetail


def _make_detail(**kwargs: object) -> DebateResultDetail:
    """Create a minimal DebateResultDetail with sensible defaults."""
    defaults: dict[str, object] = {
        "id": 1,
        "ticker": "AAPL",
        "is_fallback": False,
        "model_name": "llama-3.3-70b",
        "duration_ms": 5000,
        "total_tokens": 2000,
        "created_at": datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return DebateResultDetail(**defaults)  # type: ignore[arg-type]


class TestScanRunId:
    """Tests for the scan_run_id field on DebateResultDetail."""

    def test_defaults_to_none(self) -> None:
        """scan_run_id is None when not provided (standalone debates)."""
        detail = _make_detail()
        assert detail.scan_run_id is None

    def test_accepts_none_explicitly(self) -> None:
        """scan_run_id accepts explicit None."""
        detail = _make_detail(scan_run_id=None)
        assert detail.scan_run_id is None

    def test_accepts_integer(self) -> None:
        """scan_run_id accepts a valid integer ID."""
        detail = _make_detail(scan_run_id=42)
        assert detail.scan_run_id == 42

    def test_included_in_json_serialization(self) -> None:
        """scan_run_id is included in model_dump output."""
        detail = _make_detail(scan_run_id=42)
        data = detail.model_dump()
        assert "scan_run_id" in data
        assert data["scan_run_id"] == 42

    def test_none_in_json_serialization(self) -> None:
        """scan_run_id serializes as null when None."""
        detail = _make_detail(scan_run_id=None)
        json_str = detail.model_dump_json()
        parsed = json.loads(json_str)
        assert "scan_run_id" in parsed
        assert parsed["scan_run_id"] is None

    def test_json_roundtrip(self) -> None:
        """scan_run_id survives JSON round-trip."""
        detail = _make_detail(scan_run_id=99)
        json_str = detail.model_dump_json()
        rebuilt = DebateResultDetail.model_validate_json(json_str)
        assert rebuilt.scan_run_id == 99
