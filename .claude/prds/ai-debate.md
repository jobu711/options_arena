---
name: ai-debate
description: Three-agent AI debate system (Bull/Bear/Risk) for qualitative options analysis via Ollama
status: complete
created: 2026-02-23T21:24:08Z
updated: 2026-02-24T16:40:35Z
---

# PRD: AI Debate System (Phase 9)

## Executive Summary

Add a three-agent AI debate system to Options Arena where Bull, Bear, and Risk agents
argue over individual option contracts and produce a structured `TradeThesis` verdict.
The debate transforms quantitative scan results into qualitative reasoning: *why* a
contract is attractive, what could go wrong, and a synthesized risk assessment. Users
get conviction, not just a number.

Backend-only (Phase 9). Web UI and streaming deferred to Phase 11.

**Value proposition**: Local AI-powered multi-agent options analysis with no external
API dependencies (Ollama + Llama 3.1 8B runs entirely on user hardware). Data-driven
fallback when Ollama is unreachable ensures the tool always produces a verdict.

## Problem Statement

The MVP scan pipeline (Phases 1-8) scores and recommends contracts quantitatively:
composite scores, direction signals, delta targeting, and Greeks. But it cannot explain
*why* a contract is attractive or articulate the risks in natural language.

Users need:
- A bullish case: why this contract could profit, citing specific Greeks and indicators
- A bearish counter: what could go wrong, what risks the bull case ignores
- A synthesized verdict: weighing both sides with risk assessment and position sizing

Without qualitative reasoning, users must interpret raw numbers themselves. The debate
system bridges this gap by producing human-readable analysis grounded in the same
quantitative data the scan pipeline computes.

## User Stories

### US-1: Run Debate on Ticker
**As a** trader who has run a scan,
**I want to** run `options-arena debate AAPL` and see a structured bull/bear/risk analysis,
**So that** I understand the qualitative reasoning behind the quantitative recommendation.

**Acceptance criteria:**
- Command requires a recent scan run with scored data for the ticker
- Bull, Bear, and Risk agents each produce structured responses
- Output is Rich-formatted with colored panels for each agent and a verdict card
- Completes in < 120s on CPU with Llama 3.1 8B
- Debate is persisted to `ai_theses` table

### US-2: Data-Driven Fallback
**As a** user without Ollama installed (or when Ollama is unreachable),
**I want** the debate command to produce a data-driven verdict from quantitative signals,
**So that** I always get a recommendation regardless of LLM availability.

**Acceptance criteria:**
- Fallback activates on connection error, timeout, or `UnexpectedModelBehavior`
- Fallback thesis confidence is fixed at `0.3` (low conviction)
- Fallback reasoning synthesizes: composite score, direction, top indicator signals, Greeks
- CLI output clearly indicates this is a data-driven (non-AI) verdict
- `--fallback-only` flag bypasses Ollama entirely for testing

### US-3: View Debate History
**As a** user who has run debates previously,
**I want to** see past debate results for a ticker,
**So that** I can track how analysis has changed over time.

**Acceptance criteria:**
- `options-arena debate AAPL --history` shows recent debates from `ai_theses` table
- Shows date, direction, confidence, and summary for each debate
- Limit defaults to 5 most recent

## Requirements

### Functional Requirements

#### FR-D1: Agent Framework (PydanticAI)

Three module-level `Agent` instances using the proven PydanticAI pattern:

| Agent | Module | Output Type | Role |
|-------|--------|-------------|------|
| Bull | `agents/bull.py` | `AgentResponse` | Argue bullish case from `MarketContext` |
| Bear | `agents/bear.py` | `AgentResponse` | Counter bull's argument with bearish case |
| Risk | `agents/risk.py` | `TradeThesis` | Synthesize both sides into final verdict |

**Pattern** (Context7-verified — PydanticAI Agent API, TestModel, ModelSettings, RunUsage):
```python
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.settings import ModelSettings

# model=None at init — actual OllamaModel passed at agent.run(model=...) time
# (Context7-verified: model param defaults to None, can be overridden per-run)
bull_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,
    output_type=AgentResponse,
    retries=2,  # Context7-verified: default is 1, we override to 2
    model_settings=ModelSettings(extra_body={"num_ctx": 8192}),
    # extra_body is Context7-verified: typed as `object` in ModelSettings TypedDict
)

# Context7-verified: @agent.system_prompt supports bare decorator or (dynamic=True)
# Can take RunContext[Deps] or no args. Supports sync and async.
@bull_agent.system_prompt
async def bull_system_prompt(ctx: RunContext[DebateDeps]) -> str:
    return BULL_SYSTEM_PROMPT  # inline constant

# Context7-verified: @agent.output_validator takes (RunContext, output) -> output
# Raise ModelRetry to trigger retry with schema hints
@bull_agent.output_validator
async def reject_think_tags(ctx: RunContext[DebateDeps], output: AgentResponse) -> AgentResponse:
    if "<think>" in output.argument or "</think>" in output.argument:
        raise ModelRetry("Remove <think> tags from your response")
    return output
```

**Bear/Risk dynamic prompts** — use `@agent.system_prompt(dynamic=True)` for prompts
that depend on runtime deps (opponent argument injected at run time):
```python
# Context7-verified: dynamic=True re-evaluates prompt even with message history
@bear_agent.system_prompt(dynamic=True)
async def bear_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    base = BEAR_SYSTEM_PROMPT
    if ctx.deps.opponent_argument:
        base += f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.opponent_argument}\n<<<END_BULL_ARGUMENT>>>"
    return base
```

**Agent dependencies** (Context7-verified — `@dataclass` deps pattern):
```python
@dataclass
class DebateDeps:
    context: MarketContext
    ticker_score: TickerScore
    contracts: list[OptionContract]
    opponent_argument: str | None = None  # For bear agent (receives bull's text)
    bull_response: AgentResponse | None = None  # For risk agent
    bear_response: AgentResponse | None = None  # For risk agent
```

#### FR-D2: Debate Flow (Single-Pass)

```
1. Caller provides: TickerScore (from DB) + live Quote + TickerInfo + contracts
2. Build MarketContext (flat snapshot of all relevant data)
3. Bull agent: argue bullish case → AgentResponse
4. Bear agent: receive bull's argument + context → AgentResponse
5. Risk agent: receive both arguments + context → TradeThesis
6. Persist debate to ai_theses table
7. Return DebateResult (context + all responses + verdict + RunUsage)
```

Single-pass only (no multi-round rebuttal). Expected ~60-90s on CPU with Llama 3.1 8B.

#### FR-D3: DebateResult Model

New model in `agents/_parsing.py` (NOT in `models/analysis.py` — this is agent-internal):

```python
@dataclass
class DebateResult:
    context: MarketContext
    bull_response: AgentResponse
    bear_response: AgentResponse
    thesis: TradeThesis
    total_usage: RunUsage  # from pydantic_ai
    duration_ms: int
    is_fallback: bool  # True if data-driven, False if AI-generated
```

Not a Pydantic model — `@dataclass` suffices since `RunUsage` is a plain dataclass (not
Pydantic-serializable). `RunUsage` fields (Context7-verified): `requests: int`,
`input_tokens: int`, `output_tokens: int`, `cache_write_tokens: int`,
`cache_read_tokens: int`, `tool_calls: int`, `details: dict[str, int]`.
Persistence serializes the Pydantic sub-models individually; stores
`total_usage.input_tokens + total_usage.output_tokens` as `total_tokens` in DB.

#### FR-D4: Orchestrator

`agents/orchestrator.py` — coordinates the single-pass debate:

- Calls bull → bear → risk sequentially (each depends on prior output)
- Catches `UnexpectedModelBehavior`, `httpx.ConnectError`, `asyncio.TimeoutError`
- On any agent failure: falls back to data-driven verdict (FR-D5)
- Accumulates `RunUsage` via `__add__()` (Context7-verified): `bull_usage + bear_usage + risk_usage`
- Measures wall-clock `duration_ms` via `time.monotonic()`
- FRED-style "never raises" pattern: debate failure returns fallback, never crashes caller

```python
async def run_debate(
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    config: DebateConfig,
    repository: Repository | None = None,
) -> DebateResult:
    ...
```

#### FR-D5: Data-Driven Fallback

When Ollama is unreachable or any agent fails:

1. Synthesize `AgentResponse` for bull/bear from quantitative data:
   - `argument`: templated text citing composite score, direction, top indicators
   - `confidence`: derived from composite score (score/100 * 0.3 cap)
   - `key_points`: top 3 non-None indicator values with interpretation
   - `contracts_referenced`: from recommended contracts (strikes, expirations)
   - `model_used`: `"data-driven-fallback"`

2. Synthesize `TradeThesis`:
   - `confidence`: fixed at `0.3` (low conviction — no qualitative reasoning)
   - `summary`: "Data-driven analysis (AI unavailable). Based on composite score {X}/100, {direction} signal."
   - `bull_score` / `bear_score`: derived from indicator signals
   - `risk_assessment`: "Limited analysis — AI debate unavailable. Exercise additional caution."

3. `DebateResult.is_fallback = True` — CLI renders a warning banner

#### FR-D6: Prompt Design

Inline string constants in each agent module. Requirements:

- **Token budget**: system prompts < 1500 tokens, context block adds ~300-500 tokens
- **Flat context**: `MarketContext` rendered as key-value text, not JSON blob
- **Options-specific**: agents MUST cite specific strikes, expirations, Greeks, indicators
- **Rebuttal injection**: bear receives bull's text wrapped in `<<<BULL_ARGUMENT>>>` delimiters
  to prevent instruction bleed
- **No hallucinated data**: agents can only reference data present in `MarketContext`
- **Version header**: every prompt constant has `# VERSION: v1.0` comment

Bull prompt focuses on: upside catalysts, favorable Greeks, momentum indicators, sector strength.
Bear prompt focuses on: downside risks, unfavorable Greeks, overbought signals, macro headwinds.
Risk prompt focuses on: weighing both cases, identifying which is better-supported by data,
recommending action (buy/sell/hold) and position sizing guidance.

#### FR-D7: Model Configuration

`agents/model_config.py` — Ollama model builder:

```python
def build_ollama_model(config: DebateConfig) -> OllamaModel:
    """Build PydanticAI OllamaModel with host resolution."""
    host = _resolve_host(config)  # explicit arg > OLLAMA_HOST env > default
    return OllamaModel(config.ollama_model, base_url=host)

def _resolve_host(config: DebateConfig) -> str:
    if config.ollama_host != "http://localhost:11434":
        return config.ollama_host  # explicit config takes priority
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return env_host
    return "http://localhost:11434"
```

#### FR-D8: DebateConfig

New nested `BaseModel` on `AppSettings` (Context7-verified — pydantic-settings v2
nested `BaseModel` submodels with `env_nested_delimiter="__"`):

```python
class DebateConfig(BaseModel):
    """AI debate configuration — agent retries, context window, fallback settings."""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: float = 90.0  # per-agent timeout (seconds)
    num_ctx: int = 8192  # Ollama context window size
    retries: int = 2  # PydanticAI retry count on validation failure
    fallback_confidence: float = 0.3  # data-driven fallback confidence cap
    max_total_duration: float = 300.0  # total debate timeout (seconds)

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARENA_",
        env_nested_delimiter="__",
    )
    scan: ScanConfig = ScanConfig()
    pricing: PricingConfig = PricingConfig()
    service: ServiceConfig = ServiceConfig()
    debate: DebateConfig = DebateConfig()  # NEW
```

`ServiceConfig.ollama_host`, `ollama_model`, `ollama_timeout` remain for health checks
and other non-debate Ollama interactions. `DebateConfig` owns debate-specific settings.
Context7-verified env override: `ARENA_DEBATE__NUM_CTX=16384` maps to
`settings.debate.num_ctx == 16384`.

#### FR-D9: Persistence

**Migration** (`data/migrations/002_debate_columns.sql`):
```sql
ALTER TABLE ai_theses ADD COLUMN total_tokens INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN model_name TEXT DEFAULT '';
ALTER TABLE ai_theses ADD COLUMN duration_ms INTEGER DEFAULT 0;
ALTER TABLE ai_theses ADD COLUMN is_fallback INTEGER DEFAULT 0;
```

**Repository methods** (added to `data/repository.py`):
- `save_debate(scan_run_id, ticker, debate_result) -> int` — serialize bull/bear/thesis
  as JSON, store token count, model name, duration, fallback flag. Returns row ID.
- `get_debates_for_ticker(ticker, limit=5) -> list[DebateRow]` — returns most recent
  debates for a ticker, ordered by `created_at` DESC.

`DebateRow` is a simple dataclass (in `data/repository.py`, not `models/`) for query results.

#### FR-D10: CLI Integration

New `debate` command in `cli/commands.py`:

```
options-arena debate AAPL              # Run debate on ticker
options-arena debate AAPL --history    # Show past debates
options-arena debate AAPL --fallback-only  # Force data-driven path
```

**Typer pattern** (Context7-verified — sync def + `asyncio.run()`, boolean flags):
```python
@app.command()
def debate(
    ticker: str = typer.Argument(..., help="Ticker symbol to debate"),
    history: bool = typer.Option(False, "--history", help="Show past debates"),
    fallback_only: bool = typer.Option(False, "--fallback-only", help="Force data-driven path"),
) -> None:
    """Run AI debate on a scored ticker."""
    asyncio.run(_debate_async(ticker, history, fallback_only))
```

**Requires**: recent scan run with scored data for the ticker. If no scan data found,
print error: "No scan data for AAPL. Run: options-arena scan --preset sp500"

**Output** (Context7-verified — Rich `Panel(renderable, title=, border_style=, style=)`):
- Bull panel (green): `Panel(..., title="Bull", border_style="green")` — direction, confidence, argument, key points
- Bear panel (red): `Panel(..., title="Bear", border_style="red")` — direction, confidence, argument, key points
- Verdict card: `Panel(..., title="Verdict", border_style="blue")` — ticker, direction, confidence, summary, risk assessment
- Fallback warning banner (yellow) if `is_fallback=True`
- Token usage (`input_tokens + output_tokens`) and `duration_ms` at bottom
- **IMPORTANT**: Use `Console(stderr=True)` for logging, `Console()` for data output.
  `RichHandler(markup=False, show_path=False)` — Context7-verified params.

#### FR-D11: MarketContext Builder

New function in `agents/orchestrator.py` or `agents/_parsing.py`:

```python
def build_market_context(
    ticker_score: TickerScore,
    quote: Quote,
    ticker_info: TickerInfo,
    contracts: list[OptionContract],
) -> MarketContext:
    """Build flat MarketContext from scan pipeline output."""
```

Maps `TickerScore.signals` (indicator values), `Quote` (current price), `TickerInfo`
(sector, dividend, 52-week range), and first recommended contract (strike, delta, DTE)
into the flat `MarketContext` model.

### Non-Functional Requirements

#### NFR-1: Performance
- Per-agent timeout: 90s (configurable via `DebateConfig.ollama_timeout`)
- Total debate timeout: 300s (configurable via `DebateConfig.max_total_duration`)
- Data-driven fallback: < 1s (no LLM, pure computation)
- Target: full debate completes in < 120s on CPU with Llama 3.1 8B

#### NFR-2: Reliability
- Ollama down: graceful fallback, never crash
- Partial failure (e.g., bear agent fails): fallback for remaining agents
- Malformed LLM output: PydanticAI `retries=2` with schema hints
- `<think>` tag remnants: `@output_validator` triggers `ModelRetry`

#### NFR-3: Observability
- `logging.getLogger(__name__)` in every module — never `print()`
- Log: agent start/complete/fail, token usage, duration, fallback activation
- Persist full debate transcript to SQLite for debugging

#### NFR-4: Security
- No secrets in prompts — `MarketContext` contains only market data
- Ollama runs locally — no data leaves the machine
- Rebuttal delimiter prevents prompt injection from LLM-generated text

#### NFR-5: Testability (Context7-verified — TestModel pattern)
- All agents testable via PydanticAI `TestModel` from `pydantic_ai.models.test`
- Test pattern: `with agent.override(model=TestModel()): result = await agent.run(...)`
- `TestModel` supports `custom_output_args` for controlling structured output in tests
- Orchestrator testable with mock agents (inject `Agent` instances)
- Data-driven fallback testable in isolation
- No integration tests require Ollama installed

## Files To Create

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `agents/__init__.py` | Re-exports with `__all__` | ~20 |
| `agents/CLAUDE.md` | Module conventions and rules | ~100 |
| `agents/model_config.py` | `build_ollama_model()`, `_resolve_host()` | ~40 |
| `agents/_parsing.py` | `DebateDeps` dataclass, `DebateResult` dataclass, constants | ~60 |
| `agents/bull.py` | Bull agent + prompt constant | ~80 |
| `agents/bear.py` | Bear agent + prompt constant (receives bull argument) | ~90 |
| `agents/risk.py` | Risk agent + prompt constant (receives both arguments) | ~90 |
| `agents/orchestrator.py` | `run_debate()`, `build_market_context()`, fallback logic | ~200 |
| `data/migrations/002_debate_columns.sql` | ALTER TABLE for token/model/duration columns | ~10 |
| `tests/unit/agents/` | ~100 tests (agents, orchestrator, fallback, parsing) | ~800 |
| `tests/unit/agents/test_bull.py` | Bull agent tests with TestModel | ~100 |
| `tests/unit/agents/test_bear.py` | Bear agent tests with TestModel | ~100 |
| `tests/unit/agents/test_risk.py` | Risk agent tests with TestModel | ~100 |
| `tests/unit/agents/test_orchestrator.py` | Orchestrator tests (success, timeout, fallback) | ~200 |
| `tests/unit/agents/test_parsing.py` | DebateDeps, DebateResult, MarketContext builder | ~80 |
| `tests/integration/agents/test_debate_e2e.py` | Full debate with Ollama (`@pytest.mark.integration`) | ~50 |

## Files To Modify

| File | Change |
|------|--------|
| `models/config.py` | Add `DebateConfig(BaseModel)`, add `debate: DebateConfig` to `AppSettings` |
| `data/repository.py` | Add `save_debate()`, `get_debates_for_ticker()`, `DebateRow` dataclass |
| `cli/commands.py` | Add `debate` command (with `--history`, `--fallback-only` flags) |
| `cli/rendering.py` | Add `render_debate_panels()`, `render_debate_history()` |
| `models/__init__.py` | Re-export `DebateConfig` |
| `tests/unit/models/test_config.py` | Tests for `DebateConfig` defaults and env overrides |
| `tests/unit/data/test_repository.py` | Tests for `save_debate()`, `get_debates_for_ticker()` |

## Architecture Boundaries

| Module | Can Access | Cannot Access |
|--------|-----------|---------------|
| `agents/` | `models/`, `pydantic_ai`, `data/repository` (for persistence) | `indicators/`, `pricing/`, `services/`, `scan/`, other agents directly |
| `agents/orchestrator.py` | All agent modules, `models/`, `data/repository` | `services/` (caller fetches data), `pricing/` |
| `agents/bull.py`, `bear.py`, `risk.py` | `agents/_parsing.py`, `models/` | Each other, `services/`, `pricing/` |

Agents have NO knowledge of each other — the orchestrator coordinates them.
The orchestrator does NOT fetch data — the caller (CLI) provides `TickerScore`, `Quote`,
`TickerInfo`, and `OptionContract` list.

## Success Criteria

- [ ] `options-arena debate AAPL` completes in < 120s on CPU with Llama 3.1 8B
- [ ] Data-driven fallback produces valid `TradeThesis` when Ollama is down (confidence = 0.3)
- [ ] All three agents cite specific contracts, strikes, and Greeks from `MarketContext`
- [ ] `ai_theses` table populated with full debate transcript + metadata
- [ ] `--history` shows past debates for a ticker
- [ ] `--fallback-only` bypasses Ollama for testing
- [ ] `TestModel` tests pass without Ollama installed (~100 tests)
- [ ] `ruff check . --fix && ruff format .` — clean
- [ ] `pytest tests/ -v` — all tests pass (existing 1086 + ~100 new)
- [ ] `mypy src/ --strict` — clean
- [ ] Zero architecture boundary violations

## Constraints & Assumptions

### Assumptions
- Ollama is installed and running on `localhost:11434` (or configured via `ARENA_DEBATE__OLLAMA_HOST`)
- Llama 3.1 8B model is pulled (`ollama pull llama3.1:8b`)
- 8192 context window is sufficient for system prompt + market context + structured output
- Single-pass debate (no multi-round rebuttal) is adequate for MVP
- Recent scan data exists in SQLite for the target ticker
- yfinance provides NO Greeks — all Greeks come from `pricing/dispatch.py` via scan pipeline

### Technical Constraints
- Windows compatibility: `signal.signal()` for SIGINT, no `loop.add_signal_handler()`
- Llama 3.1 8B on CPU: ~20-30s per agent call, ~60-90s total
- PydanticAI `output_type` requires LLM to produce valid JSON matching the model schema
- `num_ctx=8192` limits total input + output tokens

### Resource Constraints
- No external API dependencies for debate (Ollama is local)
- SQLite persistence (no new database infrastructure)
- Single-threaded Ollama inference (agents run sequentially, not parallel)

## Out of Scope

- Multi-round rebuttal (single-pass only)
- Additional LLM providers beyond Ollama (defer to v2.1)
- Web UI for debate (Phase 11, separate PRD)
- SSE streaming of agent progress (Phase 11)
- Automated debate triggers (manual CLI only)
- Strategy builder / multi-leg analysis (V3)
- Prompt templating system (inline constants only)
- Parallel agent execution (sequential to respect Ollama single-thread)

## Dependencies

### Internal
- **Scan pipeline** (Phase 7): `TickerScore` with `IndicatorSignals` and recommended contracts
- **Data layer** (Phase 6): `Repository` for persistence, `Database` for migrations
- **Models** (Phase 1): `MarketContext`, `AgentResponse`, `TradeThesis`, `OptionContract`
- **CLI** (Phase 8): `cli/commands.py` for new `debate` command

### External
- **pydantic-ai** (`>= 1.62.0`): Agent framework — already installed
- **ollama** (`>= 0.6.1`): Local LLM access — already installed
- **Llama 3.1 8B**: Must be pulled by user (`ollama pull llama3.1:8b`)

## Testing Strategy

### Unit Tests (~100 tests)

**Agent tests** (using PydanticAI `TestModel`):
- Each agent produces valid output for known `MarketContext` inputs
- Confidence within [0.0, 1.0] bounds
- `contracts_referenced` is non-empty
- `<think>` tag validator triggers `ModelRetry`
- Agent handles empty/minimal `MarketContext` gracefully

**Orchestrator tests** (mock agents):
- Full success path: bull → bear → risk → persist → return
- Bull failure → fallback
- Bear failure → fallback
- Timeout → fallback
- Connection error → fallback
- `--fallback-only` mode skips Ollama
- `RunUsage` accumulation is correct
- `duration_ms` is measured correctly

**Fallback tests**:
- Data-driven `AgentResponse` has valid structure
- Data-driven `TradeThesis` has confidence = 0.3
- Fallback cites real indicator values from `TickerScore`
- `is_fallback = True` on `DebateResult`

**Persistence tests**:
- `save_debate()` round-trip with `get_debates_for_ticker()`
- Migration `002` applies cleanly on top of `001`
- JSON serialization of `AgentResponse` and `TradeThesis`

**Config tests**:
- `DebateConfig()` defaults are valid
- `ARENA_DEBATE__NUM_CTX=16384` override works
- `AppSettings()` still valid with new `debate` field

### Integration Tests (require Ollama — `@pytest.mark.integration`)
- Full debate on real ticker with Ollama running
- Verify all three agents produce meaningful output
- Verify persistence to SQLite
- Mark with `@pytest.mark.integration` — skipped in CI

## Implementation Phases

This PRD maps to a single epic with ~8-10 issues:

1. **DebateConfig + migration** — Config model, migration file, repository methods
2. **Model config + parsing** — `model_config.py`, `_parsing.py` (DebateDeps, DebateResult)
3. **Bull agent** — Agent definition, prompt, output validator
4. **Bear agent** — Agent definition, prompt (receives bull argument), output validator
5. **Risk agent** — Agent definition, prompt (receives both), output validator
6. **Orchestrator** — `run_debate()`, `build_market_context()`, error handling
7. **Data-driven fallback** — Fallback synthesis logic in orchestrator
8. **CLI integration** — `debate` command, Rich rendering, `--history`, `--fallback-only`
9. **Tests** — Unit tests for all modules + integration test
10. **Module CLAUDE.md** — `agents/CLAUDE.md` with conventions and rules

Issues 1-2 can be parallelized. Issues 3-5 can be parallelized (agents are independent).
Issue 6 depends on 3-5. Issue 7 depends on 6. Issue 8 depends on 6-7. Issue 9 spans all.

## Context7 Verification Log

All external library interfaces in this PRD were verified against current documentation
on 2026-02-23. Items marked "(Context7-verified)" in the text above.

| Library | Version | What Was Verified |
|---------|---------|-------------------|
| **pydantic-ai** | `>= 1.62.0` | `Agent.__init__` params (`model`, `output_type`, `retries`, `model_settings`); `@agent.system_prompt` decorator (bare + `dynamic=True`); `@agent.output_validator` signature; `ModelRetry` import path; `RunContext[Deps]` typing; `RunUsage` dataclass fields (`requests`, `input_tokens`, `output_tokens`, `tool_calls`, `__add__`); `ModelSettings` TypedDict (`extra_body: object`); `TestModel` from `pydantic_ai.models.test` with `agent.override()` pattern; `@dataclass` deps injection |
| **pydantic-settings** | `>= 2.13.0` | `BaseSettings` + nested `BaseModel` submodels; `SettingsConfigDict(env_prefix=, env_nested_delimiter="__")`; env var mapping e.g. `ARENA_DEBATE__NUM_CTX=16384` → `settings.debate.num_ctx`; source priority: init kwargs > env vars > defaults |
| **rich** | `>= 14.3.2` | `Panel(renderable, title=, border_style=, style=, expand=)` constructor; `Console(stderr=True)` for log separation; `RichHandler(markup=False, show_path=False, console=)` params; `markup=False` prevents bracket-style crash |
| **typer** | `>= 0.24.0` | `@app.command()` decorator; `@app.callback()` for global options; `typer.Option(False, "--flag")` for boolean flags; `typer.Argument(...)` for positional args; no native async — sync def + `asyncio.run()` |
| **pydantic** | `>= 2.12.5` | `BaseModel`, `ConfigDict(frozen=True)`, `field_validator`, `field_serializer`, `computed_field` — all pre-verified in Phase 1 models |

### Unverified Assumptions

| Item | Assumption | Risk |
|------|-----------|------|
| `OllamaModel` class | Import path is `pydantic_ai.models.ollama.OllamaModel` with `(model_name, base_url=)` constructor | Medium — verify at implementation time. Fallback: use OpenAI-compatible `OpenAIModel(model, base_url=host+"/v1")` |
| `result.usage()` | Agent run result exposes `.usage()` returning `RunUsage` | Low — v3 migration already uses this pattern successfully |
| `agent.run(model=, deps=)` | Model override at run time via `model=` kwarg | Low — documented in PydanticAI init (`model` param: "The default model") |
