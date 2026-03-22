"""Tests for ToolStatus enum, ToolResponse model, and _sanitize_error helper."""

from __future__ import annotations

import json
from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models.enums import ToolStatus
from options_arena.models.tool_response import ToolResponse

# ---------------------------------------------------------------------------
# TestToolStatus
# ---------------------------------------------------------------------------


class TestToolStatus:
    """ToolStatus enum surface tests."""

    def test_member_count(self) -> None:
        assert len(ToolStatus) == 3

    def test_values_lowercase(self) -> None:
        assert ToolStatus.SUCCESS.value == "success"
        assert ToolStatus.WARNING.value == "warning"
        assert ToolStatus.ERROR.value == "error"

    def test_is_str_enum(self) -> None:
        assert issubclass(ToolStatus, StrEnum)
        # StrEnum members are also plain str instances
        assert isinstance(ToolStatus.SUCCESS, str)


# ---------------------------------------------------------------------------
# TestToolResponse
# ---------------------------------------------------------------------------


class TestToolResponse:
    """ToolResponse generic model tests."""

    def test_success_construction(self) -> None:
        resp = ToolResponse[float](
            status=ToolStatus.SUCCESS,
            summary="Fetched quote",
            data=42.5,
            next_actions=["fetch_chain"],
        )
        assert resp.status == ToolStatus.SUCCESS
        assert resp.summary == "Fetched quote"
        assert resp.data == 42.5
        assert resp.next_actions == ["fetch_chain"]

    def test_error_construction_no_data(self) -> None:
        resp = ToolResponse[float](
            status=ToolStatus.ERROR,
            summary="Ticker not found",
        )
        assert resp.status == ToolStatus.ERROR
        assert resp.data is None
        assert resp.next_actions == []

    def test_warning_partial_data(self) -> None:
        resp = ToolResponse[dict[str, int]](
            status=ToolStatus.WARNING,
            summary="Partial data",
            data={"a": 1},
        )
        assert resp.status == ToolStatus.WARNING
        assert resp.data == {"a": 1}

    def test_frozen_rejects_mutation(self) -> None:
        resp = ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary="ok",
            data="hello",
        )
        with pytest.raises(ValidationError):
            resp.status = ToolStatus.ERROR  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        original = ToolResponse[float](
            status=ToolStatus.SUCCESS,
            summary="ok",
            data=3.14,
            next_actions=["a", "b"],
        )
        raw = original.model_dump_json()
        restored = ToolResponse[float].model_validate_json(raw)
        assert restored.status == original.status
        assert restored.summary == original.summary
        assert restored.data == original.data
        assert restored.next_actions == original.next_actions

    def test_default_next_actions_empty(self) -> None:
        resp = ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary="ok",
        )
        assert resp.next_actions == []

    def test_generic_str_type(self) -> None:
        resp = ToolResponse[str](
            status=ToolStatus.SUCCESS,
            summary="ok",
            data="hello",
        )
        assert resp.data == "hello"

    def test_generic_dict_type(self) -> None:
        resp = ToolResponse[dict[str, float]](
            status=ToolStatus.SUCCESS,
            summary="ok",
            data={"delta": 0.45, "gamma": 0.02},
        )
        assert resp.data is not None
        assert resp.data["delta"] == 0.45

    def test_model_dump_json_output(self) -> None:
        resp = ToolResponse[int](
            status=ToolStatus.SUCCESS,
            summary="count",
            data=7,
        )
        parsed = json.loads(resp.model_dump_json())
        assert parsed["status"] == "success"
        assert parsed["summary"] == "count"
        assert parsed["data"] == 7
        assert parsed["next_actions"] == []


# ---------------------------------------------------------------------------
# TestSanitizeError
# ---------------------------------------------------------------------------


class TestSanitizeError:
    """Tests for _sanitize_error helper in _toolsets.py."""

    @pytest.fixture(autouse=True)
    def _import_helper(self) -> None:
        from options_arena.agents._toolsets import _sanitize_error

        self._sanitize_error = _sanitize_error

    def test_basic_message(self) -> None:
        exc = ValueError("something broke")
        assert self._sanitize_error(exc) == "something broke"

    def test_strips_api_key(self) -> None:
        exc = RuntimeError("failed with key=gsk_abc123secret token=tok_xyz789")
        result = self._sanitize_error(exc)
        assert "gsk_abc123secret" not in result
        assert "tok_xyz789" not in result
        assert "key=***" in result
        assert "token=***" in result

    def test_truncates_long_message(self) -> None:
        exc = ValueError("x" * 200)
        result = self._sanitize_error(exc, max_len=50)
        assert len(result) == 53  # 50 chars + "..."
        assert result.endswith("...")

    def test_empty_exception(self) -> None:
        exc = Exception()
        result = self._sanitize_error(exc)
        assert result == ""
