"""Tests for agent persona identity sections in all debate prompts.

Verifies that each of the 6 debate agent prompts has a persona identity paragraph
prepended, and that PROMPT_RULES_APPENDIX is still present after the persona section.
"""

import pytest

from options_arena.agents._parsing import PROMPT_RULES_APPENDIX
from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.agents.prompts.flow_agent import FLOW_SYSTEM_PROMPT
from options_arena.agents.prompts.fundamental_agent import FUNDAMENTAL_SYSTEM_PROMPT
from options_arena.agents.prompts.risk import RISK_SYSTEM_PROMPT
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT

PROMPTS: dict[str, tuple[str, str]] = {
    "trend": (TREND_SYSTEM_PROMPT, "Momentum Trader"),
    "volatility": (VOLATILITY_SYSTEM_PROMPT, "Vol Arb Specialist"),
    "flow": (FLOW_SYSTEM_PROMPT, "Institutional Flow Analyst"),
    "fundamental": (FUNDAMENTAL_SYSTEM_PROMPT, "Event-Driven Analyst"),
    "risk": (RISK_SYSTEM_PROMPT, "Portfolio Risk Manager"),
    "contrarian": (CONTRARIAN_SYSTEM_PROMPT, "Devil's Advocate Strategist"),
}


class TestAgentPersonas:
    """Verify persona identity sections in all agent prompts."""

    @pytest.mark.parametrize("agent_name,prompt_data", PROMPTS.items())
    def test_persona_identity_present(self, agent_name: str, prompt_data: tuple[str, str]) -> None:
        """Each prompt contains its persona identity section."""
        prompt, persona_name = prompt_data
        assert f"## Your Identity: {persona_name}" in prompt

    @pytest.mark.parametrize("agent_name,prompt_data", PROMPTS.items())
    def test_rules_appendix_present(self, agent_name: str, prompt_data: tuple[str, str]) -> None:
        """Each prompt still contains PROMPT_RULES_APPENDIX."""
        prompt, _ = prompt_data
        assert PROMPT_RULES_APPENDIX in prompt

    @pytest.mark.parametrize("agent_name,prompt_data", PROMPTS.items())
    def test_persona_before_rules(self, agent_name: str, prompt_data: tuple[str, str]) -> None:
        """Persona section appears before PROMPT_RULES_APPENDIX."""
        prompt, persona_name = prompt_data
        persona_idx = prompt.index(f"## Your Identity: {persona_name}")
        rules_idx = prompt.index(PROMPT_RULES_APPENDIX)
        assert persona_idx < rules_idx

    @pytest.mark.parametrize("agent_name,prompt_data", PROMPTS.items())
    def test_persona_not_too_long(self, agent_name: str, prompt_data: tuple[str, str]) -> None:
        """Persona text is approximately 60-80 tokens (< 500 chars as proxy)."""
        prompt, persona_name = prompt_data
        header = f"## Your Identity: {persona_name}"
        start = prompt.index(header)
        # Extract from after header to next double newline (end of persona paragraph)
        after_header = prompt[start + len(header) :]
        # Persona paragraph ends at the first double newline
        para_end = after_header.index("\n\n")
        persona_body = after_header[:para_end].strip()
        # Should be a reasonable paragraph (< 500 chars, > 100 chars)
        assert len(persona_body) > 100, f"{persona_name} persona too short"
        assert len(persona_body) < 500, f"{persona_name} persona too long"

    def test_all_six_agents_covered(self) -> None:
        """All 6 debate agents have personas."""
        assert len(PROMPTS) == 6

    def test_personas_are_unique(self) -> None:
        """Each agent has a distinct persona name."""
        persona_names = [name for _, name in PROMPTS.values()]
        assert len(set(persona_names)) == 6

    @pytest.mark.parametrize("agent_name,prompt_data", PROMPTS.items())
    def test_persona_no_curly_braces(self, agent_name: str, prompt_data: tuple[str, str]) -> None:
        """Persona text contains no curly braces (safe for string concatenation)."""
        prompt, persona_name = prompt_data
        header = f"## Your Identity: {persona_name}"
        start = prompt.index(header)
        after_header = prompt[start + len(header) :]
        para_end = after_header.index("\n\n")
        persona_body = after_header[:para_end]
        assert "{" not in persona_body, f"{persona_name} persona contains curly braces"
        assert "}" not in persona_body, f"{persona_name} persona contains curly braces"
