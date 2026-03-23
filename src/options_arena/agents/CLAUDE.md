# CLAUDE.md -- Agents Module (`agents/`)

## Purpose

AI agent system for options analysis. 7 desk agents + 1 synthesis agent + recommendation
orchestrator, all via PydanticAI. Multi-provider: Groq (default) or Anthropic. Data-driven
fallback when the LLM provider is unreachable.

Agents have no knowledge of each other -- the recommendation orchestrator coordinates them.
Desk agents fetch data on-demand via tool wrappers; synthesis receives pre-fetched assessments.

## Architecture Rules

- **No inter-agent imports** -- each agent is self-contained, orchestrator coordinates
- **Desk agents fetch on-demand** -- tool wrappers in `_toolsets.py` access `services/` and `indicators/`
- **No pricing imports** -- Greeks arrive pre-computed on `OptionContract.greeks`
- **Never-raises orchestrator** -- `run_recommendation()` catches all, returns fallback `confidence=0.2`
- **`indicators/` and `analysis/` access** -- only via lazy imports in `_toolsets.py` tool wrappers

## Recommendation Orchestrator Flow

1. Build `MarketContext` from TickerScore + Quote + TickerInfo + contracts
2. Check completeness: <0.4 -> data-driven fallback; <0.6 -> warning; >=0.6 -> proceed
3. Build model from `DebateConfig` (Groq or Anthropic)
4. Phase 1 (parallel): Run 6 desk agents in recommendation mode -> `DomainAssessment` each
5. Phase 2: Synthesis agent receives all assessments + contracts -> `PositionRecommendation`
6. Persist `RecommendationResult`, return it

## Desk Agent Pattern

Each desk agent has two modes:
- **Interactive**: `run_*_desk_query()` -- plain text output for chat
- **Recommendation**: `run_*_desk_recommendation()` -- structured `DomainAssessment` output

All desk agents:
- `@output_validator` using `strip_think_tags()` + post-run defense-in-depth
- `asyncio.wait_for(agent.run(...), timeout=config.agent_timeout)` on every call
- `UsageLimits(request_limit=N+2, tool_calls_limit=N)` for budget enforcement

## Synthesis Agent

- **SynthesisDeps**: `context`, `assessments`, `contracts`, `ticker_score`, `learned_patterns`, `tuned_weights`, `tools_used`
- **Output**: `PositionRecommendation` (21 fields, Decimal prices, frozen)
- **Tools**: `build_synthesis_toolset()` -- 2 lightweight tools
- **Prompt**: `SYNTHESIS_SYSTEM_PROMPT` + `PROMPT_RULES_APPENDIX` with dynamic `<<<TUNED_WEIGHTS>>>` and `<<<LEARNED_PATTERNS>>>` injection

## Model Configuration

Multi-provider dispatch via `LLMProvider` enum in `model_config.py`:
- `LLMProvider.GROQ` -> `GroqModel` with `GroqProvider`
- `LLMProvider.ANTHROPIC` -> `AnthropicModel` with `AnthropicProvider`

## Backward Compatibility

- `DebateResult` in `_parsing.py` -- kept for existing debate record parsing
- `DebatePhase` in `_context.py` -- kept for WebSocket bridge compatibility
- `extract_agent_predictions()` -- kept for legacy outcome tracking

## Testing Patterns

- Use `TestModel` for unit tests: `with trend_desk.override(model=TestModel()):`
- Set `models.ALLOW_MODEL_REQUESTS = False` at module level in test files
- Don't test actual Groq/Anthropic responses -- use `TestModel`
- Don't assert on `RunUsage` exact token counts from `TestModel` -- they're synthetic

## What Claude Gets Wrong -- Agents-Specific

1. **Inter-agent imports** -- no agent module imports from another agent module
2. **Fetching data in agents** -- only through `_toolsets.py` tool wrappers, never direct imports
3. **Forgetting `asyncio.wait_for`** -- every `agent.run()` call must be wrapped
4. **`except Exception` without fallback** -- orchestrator must ALWAYS return a result
5. **Using `Agent(model="groq:...")`** -- use `model=None` at init, pass model at run time
6. **Forgetting `<think>` tag validator** -- all agents need `@agent.output_validator`
7. **Missing `models.ALLOW_MODEL_REQUESTS = False`** in tests
