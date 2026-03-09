# Research: prompt-engineering-v2

## PRD Summary

Extract all 6 remaining inline agent system prompts into `agents/prompts/`, build a
regression test suite that catches structural/quality regressions, and add few-shot golden
examples that demonstrate proper data citation. Creates a maintainable, testable prompt
library where every change is validated automatically.

## Relevant Existing Modules

- `agents/prompts/` — 3 files: `__init__.py`, `trend_agent.py` (extracted, v1.0), `contrarian_agent.py` (extracted, v1.0). No CLAUDE.md yet.
- `agents/_parsing.py` — `PROMPT_RULES_APPENDIX` (lines 66-93, v3.0), `compute_citation_density()` (lines 1007-1023), context renderers, `build_cleaned_*()` helpers
- `agents/bull.py` — `BULL_SYSTEM_PROMPT` (v2.1), `_REBUTTAL_PREFIX`/`_REBUTTAL_SUFFIX` (stay inline)
- `agents/bear.py` — `BEAR_SYSTEM_PROMPT` (v2.0), dynamic `opponent_argument` injection
- `agents/volatility.py` — `VOLATILITY_SYSTEM_PROMPT` (v3.0, largest: 129 lines)
- `agents/flow_agent.py` — `FLOW_SYSTEM_PROMPT` (v2.0)
- `agents/fundamental_agent.py` — `FUNDAMENTAL_SYSTEM_PROMPT` (v3.0, 67 lines)
- `agents/risk.py` — `RISK_SYSTEM_PROMPT` (v2.1) + `RISK_STRATEGY_TREE` (lines 28-37) + `RISK_V2_SYSTEM_PROMPT` (v1.0, active)
- `tests/unit/agents/` — 20 test files, `conftest.py` with 9+ fixtures, `test_prompt_enhancements.py` already validates appendix presence and version headers

## Existing Patterns to Reuse

### Extracted Prompt Pattern (from `prompts/trend_agent.py`)
```python
"""Module docstring explaining agent role and signals."""
from options_arena.agents._parsing import PROMPT_RULES_APPENDIX

# VERSION: v1.0
TREND_SYSTEM_PROMPT = (
    """System prompt content..."""
    + PROMPT_RULES_APPENDIX
)
```

### Agent Instantiation Pattern (model=None)
```python
agent: Agent[DebateDeps, OutputType] = Agent(
    model=None,  # Deferred to runtime / TestModel
    deps_type=DebateDeps,
    output_type=OutputType,
    retries=2,
    model_settings=ModelSettings(extra_body={"num_ctx": 8192}),
)
```

### Dynamic Prompt Injection Pattern
```python
@agent.system_prompt(dynamic=True)
async def dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    base = AGENT_SYSTEM_PROMPT  # Imported from prompts/
    if ctx.deps.some_field:
        base += f"\n\n<<<DELIMITER>>>\n{ctx.deps.some_field}\n<<<END_DELIMITER>>>"
    return base
```

### TestModel Testing Pattern
```python
models.ALLOW_MODEL_REQUESTS = False  # Module-level guard

@pytest.mark.asyncio
async def test_agent_output(mock_debate_deps: DebateDeps) -> None:
    with agent.override(model=TestModel()):
        result = await agent.run("Analyze AAPL", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, ExpectedOutputType)
```

### Version Header Validation Pattern (test_prompt_enhancements.py)
```python
def test_bull_source_has_v2_1_header(self) -> None:
    source = inspect.getsource(bull_module)
    assert "# VERSION: v2.1" in source
```

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|--------------|
| `agents/prompts/__init__.py` | Minimal 1-line docstring | Add re-exports for all 8 prompt constants |
| `agents/prompts/trend_agent.py` | Extracted, v1.0 | Reference pattern only (no changes) |
| `agents/prompts/contrarian_agent.py` | Extracted, v1.0 | Reference pattern only (no changes) |
| `agents/bull.py` | Inline `BULL_SYSTEM_PROMPT` + agent + validator | Remove prompt, import from `prompts/bull.py`. Keep `_REBUTTAL_*`, dynamic func, agent, validator |
| `agents/bear.py` | Inline `BEAR_SYSTEM_PROMPT` + agent + validator | Remove prompt, import from `prompts/bear.py`. Keep dynamic func, agent, validator |
| `agents/volatility.py` | Inline `VOLATILITY_SYSTEM_PROMPT` + agent + validator | Remove prompt, import from `prompts/volatility.py`. Keep dynamic func, agent, validator |
| `agents/flow_agent.py` | Inline `FLOW_SYSTEM_PROMPT` + agent + validator | Remove prompt, import from `prompts/flow_agent.py`. Keep dynamic func, agent, validator |
| `agents/fundamental_agent.py` | Inline `FUNDAMENTAL_SYSTEM_PROMPT` + agent + validator | Remove prompt, import from `prompts/fundamental_agent.py`. Keep dynamic func, agent, validator |
| `agents/risk.py` | Inline `RISK_SYSTEM_PROMPT` + `RISK_STRATEGY_TREE` + `RISK_V2_SYSTEM_PROMPT` | Remove prompts + strategy tree, import from `prompts/risk.py`. Keep dynamic funcs, agents, validators |
| `tests/unit/agents/test_prompt_enhancements.py` | 14+ tests for appendix, version headers, think-tag stripping | Extend with structure, token budget, and quality tests |

## Agent Prompt Inventory

| Agent | File | Version | Lines | Appendix | Extra Constants | Dynamic |
|-------|------|---------|-------|----------|-----------------|---------|
| Bull | bull.py | v2.1 | 34 | YES | `_REBUTTAL_PREFIX/SUFFIX` (stays) | YES |
| Bear | bear.py | v2.0 | 37 | YES | — | YES |
| Volatility | volatility.py | v3.0 | 129 | YES | — | YES (largest) |
| Flow | flow_agent.py | v2.0 | 49 | YES | — | YES |
| Fundamental | fundamental_agent.py | v3.0 | 67 | YES | — | YES |
| Risk v1 | risk.py | v2.1 | 48 | YES | `RISK_STRATEGY_TREE` (moves) | YES |
| Risk v2 | risk.py | v1.0 | 41 | YES | — | YES (active) |
| Trend | prompts/trend_agent.py | v1.0 | 48 | YES | — | NO (static) |
| Contrarian | prompts/contrarian_agent.py | v1.0 | 41 | YES | — | YES |

## Dynamic Injection Summary

| Agent | Injects | Wrapper Delimiters | Method |
|-------|---------|-------------------|--------|
| Bull | `bear_counter_argument` | `_REBUTTAL_PREFIX/SUFFIX` | String concat |
| Bear | `opponent_argument` (bull's arg) | `<<<BULL_ARGUMENT>>>` | f-string |
| Volatility | `bull_response.argument`, `bear_response.argument` | `<<<BULL/BEAR_ARGUMENT>>>` | f-string |
| Flow | `bull_response.argument`, `bear_response.argument` | `<<<BULL/BEAR_ARGUMENT>>>` | f-string |
| Fundamental | `bull_response.argument`, `bear_response.argument` | `<<<BULL/BEAR_ARGUMENT>>>` | f-string |
| Risk v2 | All Phase 1 outputs (4 structured objects) | `<<<AGENT_NAME>>>` | f-string |
| Contrarian | `all_prior_outputs` (pre-formatted text) | `<<<PRIOR_AGENT_OUTPUTS>>>` | String concat |
| Trend | None (static) | — | — |

## compute_citation_density()

**Location**: `_parsing.py:1007-1023`
**Signature**: `def compute_citation_density(context_block: str, *texts: str) -> float`
**Returns**: Float [0.0, 1.0] — fraction of `LABEL:` patterns from context cited in agent text.
**Regex**: `r"^([A-Z][A-Z0-9 /()%]+):"` (MULTILINE) for extraction, word-boundary for matching.
**Tests**: 10+ in `test_parsing.py` covering full/partial/zero citation, word boundaries, special chars.

## Token Counting Approach

No `tiktoken` or token counting utility exists in the codebase. Options:
1. **Heuristic**: `len(prompt) / 4` (~4 chars/token for English) — simple, no dependency
2. **tiktoken**: Add as optional dev dependency for accurate counting
3. **RunUsage**: Only available from real API calls, not useful for static prompt validation

**Recommendation**: Use heuristic for regression tests (< 2000 tokens ≈ < 8000 chars). If accuracy matters, add tiktoken as dev dep.

## Potential Conflicts

- **None identified**. All changes are mechanical extraction (byte-identical prompt text) + additive tests + additive few-shot examples.
- Extraction step has zero behavior change — prompts are string constants imported from a different file.
- Few-shot examples are a separate version bump after extraction.
- All existing agent tests pass unchanged (import path changes are transparent via re-exports).

## Open Questions

1. **Risk v1 vs v2**: Both `RISK_SYSTEM_PROMPT` (v1 fallback) and `RISK_V2_SYSTEM_PROMPT` (active) need extraction. Should both get few-shot examples, or only v2 (the active one)?
2. **Bull/Bear few-shot**: PRD says few-shot only for 6 active v2 agents (trend, volatility, flow, fundamental, risk, contrarian). Bull/Bear are v1 legacy — extracted but no few-shot. Confirm this scope.
3. **Token budget enforcement**: Heuristic (len/4) vs adding tiktoken dev dependency for accurate token counting in regression tests?

## Recommended Architecture

```
Wave 1: Extraction (3 parallel issues, 2 agents each)
  Issue 1: Extract bull + bear → prompts/bull.py, prompts/bear.py
  Issue 2: Extract volatility + flow → prompts/volatility.py, prompts/flow_agent.py
  Issue 3: Extract fundamental + risk → prompts/fundamental_agent.py, prompts/risk.py
  Each: Move constant, update import, verify byte-identical, run existing tests

Wave 2: Documentation
  Create agents/prompts/CLAUDE.md
  Update prompts/__init__.py with re-exports for all 8 constants

Wave 3: Test Suite (3 issues)
  Issue 1: test_prompt_structure.py — version headers, required sections, appendix presence (all 8)
  Issue 2: Token budget tests — < 2000 tokens per prompt (heuristic or tiktoken)
  Issue 3: test_prompt_quality.py — TestModel output validation, citation density > 0%

Wave 4: Few-Shot Examples (3 parallel issues, 2 agents each)
  Issue 1: trend + contrarian golden examples
  Issue 2: volatility + flow golden examples
  Issue 3: fundamental + risk golden examples
  Each: Add ## Example Output section, ACME ticker, 3+ citations, version bump
```

## Test Strategy Preview

- **Existing**: `test_prompt_enhancements.py` (14+ tests) covers appendix presence, version headers, think-tag stripping. `test_parsing.py` covers `compute_citation_density()`.
- **New test files**:
  - `test_prompt_structure.py` — Parametrized across all 8 prompts: version header, token budget, required sections, appendix concatenation
  - `test_prompt_quality.py` — TestModel-based: valid structured output, citation density > 0%, no `<think>` tags
- **Fixtures**: Reuse `conftest.py` fixtures (`mock_debate_deps`, `mock_market_context`). Add `mock_context_block` for citation density tests.
- **Pattern**: `@pytest.mark.parametrize("prompt_const", [BULL_SYSTEM_PROMPT, BEAR_SYSTEM_PROMPT, ...])` for structure tests

## Estimated Complexity

**M (Medium)** — 3-4 days

Justification:
- Wave 1 (S): Mechanical extraction — move string, update import, verify identical. 2-3 hours.
- Wave 2 (XS): CLAUDE.md + __init__.py re-exports. 30 min.
- Wave 3 (M): New test suite with parametrized structure + TestModel quality tests. 1 day.
- Wave 4 (M): Crafting golden examples with proper citation density, realistic market data (ACME), staying within token budget. 1-2 days.
