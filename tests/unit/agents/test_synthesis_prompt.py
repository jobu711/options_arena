"""Tests for synthesis agent system prompt."""

from options_arena.agents._parsing import PROMPT_RULES_APPENDIX
from options_arena.agents.prompts.synthesis import SYNTHESIS_SYSTEM_PROMPT


class TestSynthesisPrompt:
    def test_prompt_importable(self) -> None:
        """SYNTHESIS_SYSTEM_PROMPT is importable."""
        assert isinstance(SYNTHESIS_SYSTEM_PROMPT, str)

    def test_prompt_length_under_limit(self) -> None:
        """Prompt is under 8000 chars."""
        assert len(SYNTHESIS_SYSTEM_PROMPT) < 8000

    def test_prompt_contains_appendix(self) -> None:
        """Prompt includes PROMPT_RULES_APPENDIX content."""
        assert PROMPT_RULES_APPENDIX in SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_references_tuned_weights_block(self) -> None:
        """Prompt references <<<TUNED_WEIGHTS>>> delimiter."""
        assert "<<<TUNED_WEIGHTS>>>" in SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_references_learned_patterns_block(self) -> None:
        """Prompt references <<<LEARNED_PATTERNS>>> delimiter."""
        assert "<<<LEARNED_PATTERNS>>>" in SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_no_dynamic_data(self) -> None:
        """Prompt is a static string constant, not a function."""
        assert not callable(SYNTHESIS_SYSTEM_PROMPT)
