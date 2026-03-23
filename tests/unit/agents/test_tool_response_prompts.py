"""Tests for TOOL_RESPONSE_FORMAT inclusion in recommendation and synthesis prompts.

Verifies:
  - TOOL_RESPONSE_FORMAT constant exists and is non-empty
  - TOOL_RESPONSE_FORMAT is under 500 chars
  - All 7 prompts (6 recommendation + 1 synthesis) contain "Tool Response Format"
  - All 7 prompts remain under 8000 chars after insertion
"""

from __future__ import annotations

import pytest

from options_arena.agents._parsing import TOOL_RESPONSE_FORMAT
from options_arena.agents.prompts import (
    RECOMMEND_CONTRARIAN_PROMPT,
    RECOMMEND_FLOW_PROMPT,
    RECOMMEND_FUNDAMENTAL_PROMPT,
    RECOMMEND_RISK_PROMPT,
    RECOMMEND_TREND_PROMPT,
    RECOMMEND_VOLATILITY_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)

ALL_PROMPTS: list[tuple[str, str]] = [
    ("trend", RECOMMEND_TREND_PROMPT),
    ("volatility", RECOMMEND_VOLATILITY_PROMPT),
    ("flow", RECOMMEND_FLOW_PROMPT),
    ("fundamental", RECOMMEND_FUNDAMENTAL_PROMPT),
    ("risk", RECOMMEND_RISK_PROMPT),
    ("contrarian", RECOMMEND_CONTRARIAN_PROMPT),
    ("synthesis", SYNTHESIS_SYSTEM_PROMPT),
]

TOKEN_BUDGET_CHARS = 8000


class TestToolResponseFormatConstant:
    """TOOL_RESPONSE_FORMAT constant structural checks."""

    def test_exists_and_non_empty(self) -> None:
        assert isinstance(TOOL_RESPONSE_FORMAT, str)
        assert len(TOOL_RESPONSE_FORMAT) > 0

    def test_under_500_chars(self) -> None:
        assert len(TOOL_RESPONSE_FORMAT) < 500, (
            f"TOOL_RESPONSE_FORMAT is {len(TOOL_RESPONSE_FORMAT)} chars, expected < 500"
        )


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
class TestToolResponseInPrompts:
    """Verify TOOL_RESPONSE_FORMAT is embedded in all 7 prompts."""

    @pytest.mark.critical
    def test_contains_tool_response_format_heading(self, prompt_name: str, prompt: str) -> None:
        """Each prompt contains the 'Tool Response Format' section heading."""
        assert "Tool Response Format" in prompt, (
            f"{prompt_name} prompt is missing 'Tool Response Format' section"
        )

    def test_prompt_under_budget(self, prompt_name: str, prompt: str) -> None:
        """Each prompt stays under 8000 chars after TOOL_RESPONSE_FORMAT insertion."""
        assert len(prompt) < TOKEN_BUDGET_CHARS, (
            f"{prompt_name} prompt is {len(prompt)} chars, exceeds budget of {TOKEN_BUDGET_CHARS}"
        )
