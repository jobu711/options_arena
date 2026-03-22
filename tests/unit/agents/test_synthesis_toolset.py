"""Tests for synthesis toolset."""

from __future__ import annotations

import pytest
from pydantic_ai import models

from options_arena.agents._toolsets import (
    build_synthesis_toolset,
    synth_fetch_chain_summary,
    synth_fetch_current_quote,
)

models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.critical
class TestSynthesisToolset:
    """Tests for build_synthesis_toolset and its tool functions."""

    def test_returns_list(self) -> None:
        result = build_synthesis_toolset()
        assert isinstance(result, list)

    def test_non_empty(self) -> None:
        result = build_synthesis_toolset()
        assert len(result) > 0

    def test_has_expected_tools(self) -> None:
        result = build_synthesis_toolset()
        assert synth_fetch_current_quote in result
        assert synth_fetch_chain_summary in result

    def test_tool_count(self) -> None:
        result = build_synthesis_toolset()
        assert len(result) == 2

    def test_tools_are_callable(self) -> None:
        for tool in build_synthesis_toolset():
            assert callable(tool)

    def test_tool_names(self) -> None:
        tools = build_synthesis_toolset()
        names = [t.__name__ for t in tools]  # type: ignore[union-attr]
        assert "synth_fetch_current_quote" in names
        assert "synth_fetch_chain_summary" in names
