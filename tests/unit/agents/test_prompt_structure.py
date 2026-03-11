"""Structural regression tests for all 8 agent system prompts.

Tests cover:
  - Each prompt contains PROMPT_RULES_APPENDIX text
  - Each prompt ends with PROMPT_RULES_APPENDIX
  - Each prompt is within the token budget (< 8500 chars)
  - Each prompt is a non-empty string
  - Each prompt is str type
  - No raw f-string placeholders in static prompts
  - Risk-specific content appears only in the risk prompt
  - VERSION header presence in prompt source files
"""

from __future__ import annotations

import re

import pytest

from options_arena.agents._parsing import PROMPT_RULES_APPENDIX
from options_arena.agents.bear import BEAR_SYSTEM_PROMPT
from options_arena.agents.bull import BULL_SYSTEM_PROMPT
from options_arena.agents.flow_agent import FLOW_SYSTEM_PROMPT
from options_arena.agents.fundamental_agent import FUNDAMENTAL_SYSTEM_PROMPT
from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.agents.risk import RISK_SYSTEM_PROMPT
from options_arena.agents.volatility import VOLATILITY_SYSTEM_PROMPT

# All 8 prompts as parametrize tuples: (name, prompt_constant)
ALL_PROMPTS: list[tuple[str, str]] = [
    ("bull", BULL_SYSTEM_PROMPT),
    ("bear", BEAR_SYSTEM_PROMPT),
    ("volatility", VOLATILITY_SYSTEM_PROMPT),
    ("flow", FLOW_SYSTEM_PROMPT),
    ("fundamental", FUNDAMENTAL_SYSTEM_PROMPT),
    ("risk", RISK_SYSTEM_PROMPT),
    ("trend", TREND_SYSTEM_PROMPT),
    ("contrarian", CONTRARIAN_SYSTEM_PROMPT),
]

# Maximum character budget for any single prompt before few-shot examples
TOKEN_BUDGET_CHARS = 8500

# Regex to detect raw f-string placeholders like {variable_name}
# Excludes JSON schema examples like {"key": ...} and {0.0-1.0}
_FSTRING_PLACEHOLDER_RE = re.compile(
    r"\{[a-z_][a-z0-9_]*\}",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
@pytest.mark.critical
def test_contains_appendix(prompt_name: str, prompt: str) -> None:
    """Each prompt contains the shared PROMPT_RULES_APPENDIX text."""
    # Check for a distinctive substring from the appendix
    assert "Confidence calibration" in prompt, (
        f"{prompt_name} prompt does not contain PROMPT_RULES_APPENDIX"
    )
    assert "Data citation rules" in prompt, (
        f"{prompt_name} prompt is missing data citation rules from appendix"
    )


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
def test_ends_with_appendix(prompt_name: str, prompt: str) -> None:
    """Each prompt ends with PROMPT_RULES_APPENDIX content."""
    assert prompt.endswith(PROMPT_RULES_APPENDIX), (
        f"{prompt_name} prompt does not end with PROMPT_RULES_APPENDIX"
    )


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
def test_within_token_budget(prompt_name: str, prompt: str) -> None:
    """Each prompt is within the character budget (< 8500 chars)."""
    assert len(prompt) < TOKEN_BUDGET_CHARS, (
        f"{prompt_name} prompt is {len(prompt)} chars, exceeds budget of {TOKEN_BUDGET_CHARS}"
    )


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
def test_not_empty(prompt_name: str, prompt: str) -> None:
    """Each prompt is a non-empty string."""
    assert prompt.strip(), f"{prompt_name} prompt is empty"


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
def test_is_string_type(prompt_name: str, prompt: str) -> None:
    """Each prompt is of str type."""
    assert isinstance(prompt, str), f"{prompt_name} prompt is {type(prompt)}, expected str"


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_PROMPTS,
    ids=[name for name, _ in ALL_PROMPTS],
)
def test_no_raw_fstring_placeholders(prompt_name: str, prompt: str) -> None:
    """Static prompts should not contain raw f-string placeholders like {variable}.

    Prompts use string concatenation, not f-strings. Placeholders would indicate
    an unresolved template variable that would appear literally in the prompt.
    """
    matches = _FSTRING_PLACEHOLDER_RE.findall(prompt)
    # Filter out known JSON schema examples that look like placeholders
    # e.g., {0.0-1.0} in the JSON schema, {num_ctx} in extra_body docs
    false_positives = {"model_used", "model_name"}
    real_matches = [m for m in matches if m.strip("{}") not in false_positives]
    assert not real_matches, (
        f"{prompt_name} prompt contains raw f-string placeholders: {real_matches}"
    )


class TestVersionHeaders:
    """Verify VERSION headers in prompt source files.

    Prompt template files in ``agents/prompts/`` must contain a
    ``# VERSION: vX.Y`` header in their module docstring.
    """

    # Source modules containing prompt constants — point at prompts/ submodules
    _PROMPT_SOURCES = [
        ("bull", "options_arena.agents.prompts.bull"),
        ("bear", "options_arena.agents.prompts.bear"),
        ("volatility", "options_arena.agents.prompts.volatility"),
        ("flow", "options_arena.agents.prompts.flow_agent"),
        ("fundamental", "options_arena.agents.prompts.fundamental_agent"),
        ("risk", "options_arena.agents.prompts.risk"),
        ("trend", "options_arena.agents.prompts.trend_agent"),
        ("contrarian", "options_arena.agents.prompts.contrarian_agent"),
    ]

    _VERSION_RE = re.compile(r"^# VERSION: v\d+\.\d+", re.MULTILINE)

    @pytest.mark.parametrize(
        ("agent_name", "module_path"),
        _PROMPT_SOURCES,
        ids=[name for name, _ in _PROMPT_SOURCES],
    )
    def test_version_header_presence_documented(self, agent_name: str, module_path: str) -> None:
        """Each prompt source file contains a ``# VERSION: vX.Y`` header."""
        import importlib
        import inspect

        module = importlib.import_module(module_path)
        source_file = inspect.getfile(module)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()

        assert self._VERSION_RE.search(source), (
            f"{agent_name} prompt source ({module_path}) is missing '# VERSION: vX.Y' header"
        )


class TestRiskSpecific:
    """Verify risk-specific content appears only in the risk prompt."""

    def test_risk_prompt_contains_risk_level(self) -> None:
        """Risk prompt references risk levels (low/moderate/high/extreme)."""
        assert "risk_level" in RISK_SYSTEM_PROMPT
        assert "low" in RISK_SYSTEM_PROMPT
        assert "moderate" in RISK_SYSTEM_PROMPT
        assert "high" in RISK_SYSTEM_PROMPT
        assert "extreme" in RISK_SYSTEM_PROMPT

    def test_risk_prompt_contains_pop_estimate(self) -> None:
        """Risk prompt references probability of profit estimation."""
        assert "pop_estimate" in RISK_SYSTEM_PROMPT

    def test_risk_prompt_contains_position_sizing(self) -> None:
        """Risk prompt references position sizing guidance."""
        prompt_lower = RISK_SYSTEM_PROMPT.lower()
        assert "position_size" in prompt_lower or "position sizing" in prompt_lower

    def test_risk_prompt_contains_charm_decay(self) -> None:
        """Risk prompt references charm/delta decay assessment."""
        assert "charm" in RISK_SYSTEM_PROMPT.lower()

    def test_risk_prompt_contains_spread_quality(self) -> None:
        """Risk prompt references bid-ask spread quality assessment."""
        assert "spread" in RISK_SYSTEM_PROMPT.lower()

    def test_risk_level_not_in_non_risk_prompts(self) -> None:
        """The risk_level schema field does not appear in non-risk prompts."""
        non_risk_prompts = [(name, prompt) for name, prompt in ALL_PROMPTS if name != "risk"]
        for name, prompt in non_risk_prompts:
            # "risk_level" as a JSON key is risk-specific
            assert '"risk_level"' not in prompt, (
                f"{name} prompt should not contain risk_level schema field"
            )
