# CLAUDE.md — Agents Module (`agents/`)

## Purpose

AI agent system for options analysis. 7 desk agents + 1 synthesis agent + recommendation
orchestrator, all via PydanticAI. Multi-provider: **Groq** (default, Llama 3.3 70B) or
**Anthropic** (Claude, `--provider anthropic`). Data-driven fallback when the LLM provider
is unreachable ensures the tool always produces a recommendation.

Agents have **no knowledge of each other** — the recommendation orchestrator coordinates them.
Desk agents fetch data on-demand via tool wrappers; the synthesis agent receives pre-fetched
domain assessments.

## Files

| File | Purpose | Pattern |
|------|---------|---------|
| `CLAUDE.md` | Module conventions and rules | -- |
| `recommendation_orchestrator.py` | `run_recommendation()` — primary entry point. Runs 6 desk agents in parallel, collects `DomainAssessment`, runs synthesis agent, persists `RecommendationResult` | Coordinator |
| `synthesis_agent.py` | `synthesis_agent: Agent[SynthesisDeps, PositionRecommendation]` — weighs 6 domain assessments, selects contract, defines entry/exit | PydanticAI Agent |
| `model_config.py` | `build_debate_model()` — multi-provider model builder (Groq/Anthropic) | Config utility |
| `_context.py` | `build_market_context()`, `classify_macd_signal()`, `extract_agent_predictions()`, `DebatePhase` (backward compat), `effective_batch_ticker_delay()` | Context utilities |
| `_parsing.py` | `DebateResult` (backward compat), `strip_think_tags()`, `PROMPT_RULES_APPENDIX`, `render_context_block()`, domain-specific renderers, `compute_citation_density()` | Internal |
| `_desk_deps.py` | `DeskDeps` dataclass — shared deps for all desk agents | Internal |
| `_toolsets.py` | Per-desk + synthesis toolset builders (`build_*_toolset()`), `TICKER_RE` validation, `isfinite()` guards | Internal |
| `_routing.py` | `classify_intent()`, `route_query()` — intent classification + desk dispatch for agency | Internal |
| `constraints.py` | Deterministic contract constraint pre-check (hard/soft violations) | Validation |
| `trend_desk.py` | Trend desk agent — interactive queries + recommendation mode | PydanticAI Agent |
| `volatility_desk.py` | Volatility desk agent — IV, term structure, regime | PydanticAI Agent |
| `flow_desk.py` | Flow desk agent — put/call ratio, volume, unusual activity | PydanticAI Agent |
| `fundamental_desk.py` | Fundamental desk agent — earnings, dividends, sector valuation | PydanticAI Agent |
| `risk_desk.py` | Risk desk agent — portfolio risk, position sizing, hedging | PydanticAI Agent |
| `contrarian_desk.py` | Contrarian desk agent — challenges consensus, finds blind spots | PydanticAI Agent |
| `research_desk.py` | Research desk agent — cross-domain analysis | PydanticAI Agent |
| `__init__.py` | Re-exports: `run_recommendation`, `RecommendationProgressCallback`, `build_market_context`, `classify_macd_signal`, `DebatePhase`, `build_debate_model`, `render_context_block`, desk agents, toolsets, routing, synthesis | Standard |

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **No inter-agent imports** | No agent module imports from any other agent module. Each agent is self-contained. |
| **Orchestrator coordinates** | `recommendation_orchestrator.py` runs desk agents, collects assessments, invokes synthesis. |
| **Desk agents fetch on-demand** | Desk tool wrappers (`_toolsets.py`) access `services/` and `indicators/` for on-demand computation. |
| **No pricing** | Agents never import from `pricing/`. All Greeks arrive pre-computed on `OptionContract.greeks`. |
| **Typed boundaries** | `run_recommendation()` returns `RecommendationResult`. No raw dicts. |
| **Logging only** | `logging.getLogger(__name__)` — never `print()`. |
| **Never-raises orchestrator** | `run_recommendation()` catches all exceptions, returns fallback with `confidence=0.2`. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (MarketContext, PositionRecommendation, DomainAssessment, enums, config) | `services/` (except via _toolsets.py desk tool wrappers) |
| `agents/_parsing.py` (DebateResult, constants, renderers) | `pricing/` (Greeks pre-computed) |
| `agents/_context.py` (build_market_context, DebatePhase) | `scoring/`, `scan/` |
| `data/repository` (persistence, from orchestrator + desk tools) | Other agent modules (agents don't know each other) |
| `indicators/` (desk tool wrappers in `_toolsets.py` only — lazy imports) | `cli/`, `reporting/` |
| `analysis/` (desk tool wrappers in `_toolsets.py` only — lazy imports) | -- |
| `pydantic_ai` (Agent, RunContext, ModelRetry, ModelSettings) | -- |
| stdlib: `asyncio`, `logging`, `time`, `os`, `dataclasses` | -- |

---

## Recommendation Orchestrator Flow

```text
1. Build MarketContext from TickerScore + Quote + TickerInfo + contracts
2. Check completeness: <0.4 -> data-driven fallback; <0.6 -> warning; >=0.6 -> proceed
3. Build model from DebateConfig (Groq or Anthropic)
4. Phase 1 (parallel): Run 6 desk agents in recommendation mode
   - Each produces a DomainAssessment (TrendAssessment, VolatilityAssessment, etc.)
5. Phase 2: Synthesis agent receives all assessments + contracts
   - Produces PositionRecommendation (contract, entry/exit, direction, confidence)
6. Persist RecommendationResult to recommendation_results table
7. Return RecommendationResult
```

### Error Handling — Never-Raises Pattern

```python
async def run_recommendation(
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    config: DebateConfig,
    repository: Repository | None = None,
    progress: RecommendationProgressCallback | None = None,
    ...
) -> RecommendationResult:
    """Run recommendation pipeline. On any failure, return fallback — never raises."""
```

---

## Desk Agent Pattern

Each desk agent has two modes:
- **Interactive**: `run_*_desk_query()` — plain text output for chat
- **Recommendation**: `run_*_desk_recommendation()` — structured `DomainAssessment` output

```python
# Interactive mode
trend_desk: Agent[DeskDeps, str] = Agent(model=None, deps_type=DeskDeps, output_type=str)

# Recommendation mode
trend_desk_recommend: Agent[DeskDeps, TrendAssessment] = Agent(
    model=None, deps_type=DeskDeps, output_type=TrendAssessment
)
```

All desk agents: `@output_validator` using `strip_think_tags()` + post-run defense-in-depth.
`asyncio.wait_for(agent.run(...), timeout=config.agent_timeout)` on every call.
`UsageLimits(request_limit=N+2, tool_calls_limit=N)` for budget enforcement.

---

## Synthesis Agent

```python
synthesis_agent: Agent[SynthesisDeps, PositionRecommendation] = Agent(
    model=None, deps_type=SynthesisDeps, output_type=PositionRecommendation
)
```

- **SynthesisDeps**: `context`, `assessments`, `contracts`, `ticker_score`, `learned_patterns`, `tuned_weights`, `tools_used`
- **Output**: `PositionRecommendation` (21 fields, Decimal prices, frozen)
- **Tools**: `build_synthesis_toolset()` — 2 lightweight tools (`synth_fetch_current_quote`, `synth_fetch_chain_summary`)
- **Prompt**: `SYNTHESIS_SYSTEM_PROMPT` + `PROMPT_RULES_APPENDIX`. Dynamic injection of `<<<TUNED_WEIGHTS>>>` and `<<<LEARNED_PATTERNS>>>` blocks

---

## Model Configuration

Multi-provider dispatch via `LLMProvider` enum in `model_config.py`.

```python
def build_debate_model(config: DebateConfig) -> Model:
    match config.provider:
        case LLMProvider.GROQ:
            return GroqModel(config.model, provider=GroqProvider(api_key=api_key))
        case LLMProvider.ANTHROPIC:
            return AnthropicModel(config.anthropic_model, provider=AnthropicProvider(api_key=api_key))
```

---

## Backward Compatibility

- `DebateResult` in `_parsing.py` — kept for backward-compat data parsing (existing debate records)
- `DebatePhase` in `_context.py` — kept for WebSocket bridge compatibility
- `extract_agent_predictions()` in `_context.py` — kept for outcome tracking of legacy debates
- `build_market_context()` in `_context.py` — shared by recommendation orchestrator

---

## Testing Patterns

### TestModel for Unit Tests

```python
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

models.ALLOW_MODEL_REQUESTS = False

@pytest.mark.asyncio
async def test_desk_agent() -> None:
    with trend_desk.override(model=TestModel()):
        result = await trend_desk.run("Analyze AAPL", deps=deps)
    assert isinstance(result.output, str)
```

### What NOT to Test

- Don't test actual Groq/Anthropic responses in unit tests — use `TestModel`
- Don't test prompt quality (subjective) — test prompt structure
- Don't assert on `RunUsage` exact token counts from `TestModel` — they're synthetic

---

## What Claude Gets Wrong — Agents-Specific (Fix These)

1. **Inter-agent imports** — No agent module imports from any other agent module.
2. **Fetching data in agents** — Desk agents access services ONLY through `_toolsets.py` tool wrappers, never direct imports.
3. **`async def` on Typer command** — CLI commands are sync + `asyncio.run()`.
4. **Forgetting `asyncio.wait_for` on agent.run()** — Every `agent.run()` call must be wrapped.
5. **`except Exception` without fallback** — The orchestrator must ALWAYS return a result.
6. **Using `Agent(model="groq:...")`** — Use `model=None` at init, pass model at `agent.run(model=...)` time.
7. **Forgetting the `<think>` tag validator** — All agents need `@agent.output_validator`.
8. **`markup=True` in Rich panels** — Use `markup=False` for agent output.
9. **Assuming yfinance provides Greeks** — All Greeks from `pricing/dispatch.py`.
10. **`Optional[X]` syntax** — Use `X | None`. Python 3.13+.
11. **Missing `models.ALLOW_MODEL_REQUESTS = False` in tests**.
12. **`print()` in agent code** — Use `logging.getLogger(__name__)`.
