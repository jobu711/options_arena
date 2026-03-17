"""Tests for desk agent prompts -- quality gates."""

from __future__ import annotations

import pytest


@pytest.mark.critical
class TestDeskVolatilityPrompt:
    """DESK_VOLATILITY_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        assert isinstance(DESK_VOLATILITY_PROMPT, str)
        assert len(DESK_VOLATILITY_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        assert len(DESK_VOLATILITY_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_VOLATILITY_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        assert "fetch_quote" in DESK_VOLATILITY_PROMPT
        assert "fetch_vol_surface_slice" in DESK_VOLATILITY_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_VOLATILITY_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT

        assert "VERSION" in DESK_VOLATILITY_PROMPT
