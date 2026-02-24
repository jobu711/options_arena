# CLAUDE.md — Agents Module (`agents/`)

## Purpose

Three-agent AI debate system for qualitative options analysis. Bull, Bear, and Risk
agents run sequentially via PydanticAI + Ollama (Llama 3.1 8B), transforming quantitative
scan results into human-readable reasoning. Data-driven fallback when Ollama is unreachable
ensures the tool always produces a verdict.

Agents have **no knowledge of each other** — the orchestrator coordinates them.
The orchestrator does **not fetch data** — the caller (CLI) provides all inputs.

## Files

| File | Purpose | Pattern |
|------|---------|---------|
| `CLAUDE.md` | Module conventions and rules | — |
| `model_config.py` | `build_ollama_model()`, `_resolve_host()` | Config utility |
| `_parsing.py` | `DebateDeps` dataclass, `DebateResult` dataclass, constants | Internal |
| `bull.py` | Bull agent + system prompt + output validator | PydanticAI Agent |
| `bear.py` | Bear agent + dynamic prompt (receives bull argument) | PydanticAI Agent |
| `risk.py` | Risk agent + dynamic prompt (receives both arguments) | PydanticAI Agent |
| `orchestrator.py` | `run_debate()`, `build_market_context()`, fallback logic | Coordinator |
| `__init__.py` | Re-exports `run_debate`, `DebateResult`, `build_market_context` with `__all__` | Standard |

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **No inter-agent imports** | `bull.py` never imports from `bear.py` or `risk.py`. Each agent is self-contained. |
| **Orchestrator coordinates** | Only `orchestrator.py` imports from agent modules. Agents import from `_parsing.py` only. |
| **No data fetching** | Agents and orchestrator receive pre-fetched data. No `httpx`, `yfinance`, or service imports. |
| **No pricing** | Agents never import from `pricing/`. All Greeks arrive pre-computed on `OptionContract.greeks`. |
| **Typed boundaries** | `run_debate()` returns `DebateResult`. Agent outputs are `AgentResponse` or `TradeThesis`. No raw dicts. |
| **Logging only** | `logging.getLogger(__name__)` — never `print()`. Log agent start/complete/fail, token usage, fallback. |
| **Never-raises orchestrator** | `run_debate()` follows FRED-style pattern: debate failure returns fallback, never crashes caller. |

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (MarketContext, AgentResponse, TradeThesis, OptionContract, enums, config) | `services/` (no data fetching) |
| `agents/_parsing.py` (DebateDeps, DebateResult, constants) | `pricing/` (Greeks pre-computed) |
| `data/repository` (persistence only, from orchestrator) | `indicators/`, `scoring/`, `scan/` |
| `pydantic_ai` (Agent, RunContext, ModelRetry, ModelSettings) | Other agent modules (bull/bear/risk don't know each other) |
| stdlib: `asyncio`, `logging`, `time`, `os`, `dataclasses` | `cli/`, `reporting/`, `analysis/` |

---

## PydanticAI Agent Pattern (Context7-Verified)

### Agent Definition

Module-level `Agent` instances — no classes. `model=None` at init, actual model passed
at `agent.run(model=...)` time.

```python
from dataclasses import dataclass
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.settings import ModelSettings

from options_arena.agents._parsing import DebateDeps
from options_arena.models import AgentResponse

# Context7-verified: Agent.__init__ params:
#   model (default None), output_type, retries (default 1),
#   deps_type, model_settings, instructions
bull_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,                         # overridden per-run
    deps_type=DebateDeps,               # Context7-verified: type-checks deps in run()
    output_type=AgentResponse,          # Context7-verified: enforces structured JSON output
    retries=2,                          # Context7-verified: default is 1, override to 2
    model_settings=ModelSettings(
        extra_body={"num_ctx": 8192},   # Context7-verified: extra_body typed as `object`
    ),
)
```

### System Prompt Decorator (Context7-Verified)

Two forms — bare decorator for static prompts, `dynamic=True` for runtime-dependent prompts:

```python
# Static prompt — evaluated once, cached for message_history reuse
# Context7-verified: bare decorator, no-arg function returning str
@bull_agent.system_prompt
def bull_system_prompt() -> str:
    return BULL_SYSTEM_PROMPT

# Dynamic prompt — re-evaluated even when message_history is provided
# Context7-verified: dynamic=True, takes RunContext[Deps], sync or async
@bear_agent.system_prompt(dynamic=True)
async def bear_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    base = BEAR_SYSTEM_PROMPT
    if ctx.deps.opponent_argument:
        base += f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.opponent_argument}\n<<<END_BULL_ARGUMENT>>>"
    return base
```

**When to use `dynamic=True`**: Bear and Risk agents need runtime data (opponent arguments)
injected into their prompts. Bull uses a static prompt (no opponent argument yet).

### Output Validator (Context7-Verified)

Validates LLM output after Pydantic parsing. Raises `ModelRetry` to trigger retry with
schema hints (up to `retries` count).

```python
# Context7-verified: signature overloads — can take (RunContext, output) or just (output)
# Raise ModelRetry to trigger retry with corrective message
@bull_agent.output_validator
async def reject_think_tags(
    ctx: RunContext[DebateDeps], output: AgentResponse,
) -> AgentResponse:
    if "<think>" in output.argument or "</think>" in output.argument:
        raise ModelRetry("Remove <think> tags from your response")
    return output
```

**All three agents** must have this validator. Llama 3.1 8B sometimes emits `<think>` tags
from its reasoning trace. Without the validator, these leak into the user-facing argument text.

### Running an Agent (Context7-Verified)

```python
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.usage import RunUsage

model = build_ollama_model(config)
deps = DebateDeps(context=market_ctx, ticker_score=score, contracts=contracts)

# Context7-verified: agent.run() params — model override, deps injection
result = await asyncio.wait_for(
    bull_agent.run(
        f"Analyze {market_ctx.ticker} for a bullish options position.",
        model=model,       # Context7-verified: overrides Agent.__init__ model
        deps=deps,         # Context7-verified: type-checked against deps_type
    ),
    timeout=config.ollama_timeout,
)

output: AgentResponse = result.output       # typed output
usage: RunUsage = result.usage()            # Context7-verified: returns RunUsage
```

### Agent Override for Testing (Context7-Verified)

```python
from pydantic_ai.models.test import TestModel

# Context7-verified: agent.override() is a context manager
# TestModel accepts custom_output_args for controlling structured output
with bull_agent.override(model=TestModel()):
    result = await bull_agent.run("test prompt", deps=deps)
    assert isinstance(result.output, AgentResponse)
```

---

## Dependencies Dataclass

```python
@dataclass
class DebateDeps:
    """Injected into every agent via RunContext[DebateDeps]."""
    context: MarketContext
    ticker_score: TickerScore
    contracts: list[OptionContract]
    opponent_argument: str | None = None      # For bear (receives bull's text)
    bull_response: AgentResponse | None = None  # For risk agent
    bear_response: AgentResponse | None = None  # For risk agent
```

**Why `@dataclass` not Pydantic**: PydanticAI's `deps_type` expects a plain type. Dataclass
is the documented pattern (Context7-verified). No validation needed — deps are constructed
by the orchestrator from already-validated models.

---

## DebateResult

```python
@dataclass
class DebateResult:
    """Complete debate output returned by run_debate()."""
    context: MarketContext
    bull_response: AgentResponse
    bear_response: AgentResponse
    thesis: TradeThesis
    total_usage: RunUsage        # from pydantic_ai — accumulated via __add__
    duration_ms: int
    is_fallback: bool            # True if data-driven, False if AI-generated
```

**Why `@dataclass` not Pydantic**: `RunUsage` is a plain dataclass (not Pydantic-serializable).
Persistence serializes the Pydantic sub-models individually; stores
`total_usage.input_tokens + total_usage.output_tokens` as `total_tokens` in DB.

---

## RunUsage Accumulation (Context7-Verified)

```python
# Context7-verified: RunUsage fields:
#   requests: int, input_tokens: int, output_tokens: int,
#   cache_write_tokens: int, cache_read_tokens: int,
#   tool_calls: int, details: dict[str, int]
# Context7-verified: RunUsage.__add__ sums all fields
total_usage = bull_result.usage() + bear_result.usage() + risk_result.usage()
```

---

## Model Configuration

```python
from pydantic_ai.models.ollama import OllamaModel

def build_ollama_model(config: DebateConfig) -> OllamaModel:
    """Build PydanticAI OllamaModel with host resolution.

    Host priority: explicit config > OLLAMA_HOST env var > default localhost.
    """
    host = _resolve_host(config)
    return OllamaModel(config.ollama_model, base_url=host)

def _resolve_host(config: DebateConfig) -> str:
    if config.ollama_host != "http://localhost:11434":
        return config.ollama_host
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return env_host
    return "http://localhost:11434"
```

**Import path**: `from pydantic_ai.models.ollama import OllamaModel` — verify at
implementation time. Fallback: `from pydantic_ai.models.openai import OpenAIModel` with
`base_url=host + "/v1"` (Ollama exposes an OpenAI-compatible endpoint).

---

## Orchestrator Flow

```
1. Build MarketContext from TickerScore + Quote + TickerInfo + contracts
2. Build OllamaModel from DebateConfig
3. Bull agent: argue bullish case → AgentResponse
4. Bear agent: receive bull's argument + context → AgentResponse
5. Risk agent: receive both arguments + context → TradeThesis
6. Accumulate RunUsage: bull + bear + risk
7. Persist debate to ai_theses table (if repository provided)
8. Return DebateResult
```

### Error Handling — Never-Raises Pattern

```python
async def run_debate(
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    config: DebateConfig,
    repository: Repository | None = None,
) -> DebateResult:
    """Run debate. On any failure, return data-driven fallback — never raises."""
    try:
        # ... build context, run agents sequentially
        pass
    except (
        UnexpectedModelBehavior,   # PydanticAI: LLM returned invalid output after retries
        httpx.ConnectError,        # Ollama not running
        TimeoutError,              # Per-agent or total timeout
        Exception,                 # Catch-all for unexpected failures
    ) as e:
        logger.warning("Debate failed (%s), using data-driven fallback", type(e).__name__)
        return _build_fallback_result(context, ticker_score, contracts)
```

**Timeout strategy**:
- Per-agent: `asyncio.wait_for(agent.run(...), timeout=config.ollama_timeout)` (90s default)
- Total debate: `asyncio.wait_for(_run_all_agents(...), timeout=config.max_total_duration)` (300s default)
- Fallback computation: < 1s (no LLM, pure string formatting)

### `build_market_context()` Mapping

| Source | MarketContext Field |
|--------|-------------------|
| `TickerScore.ticker` | `ticker` |
| `Quote.price` | `current_price` |
| `TickerInfo.fifty_two_week_high/low` | `price_52w_high/low` |
| `TickerScore.signals.rsi` | `rsi_14` |
| `TickerInfo.sector` | `sector` |
| `TickerInfo.dividend_yield` | `dividend_yield` |
| First contract's `strike`, `greeks.delta` | `target_strike`, `target_delta` |
| First contract's `dte` | `dte_target` |
| `ExerciseStyle.AMERICAN` (always for US equity) | `exercise_style` |

Fields like `iv_rank`, `iv_percentile`, `atm_iv_30d`, `put_call_ratio` may be `None` on
`TickerScore.signals` — use `0.0` as safe default for `MarketContext` (required float fields).

---

## Data-Driven Fallback

When Ollama is unreachable or any agent fails:

1. **Synthesize `AgentResponse`** for bull and bear from quantitative data:
   - `argument`: templated text citing composite score, direction, top indicators
   - `confidence`: derived from composite score (`score / 100 * 0.3` cap)
   - `key_points`: top 3 non-None indicator values with interpretation
   - `contracts_referenced`: from recommended contracts (strikes, expirations)
   - `model_used`: `"data-driven-fallback"`

2. **Synthesize `TradeThesis`**:
   - `confidence`: fixed at `config.fallback_confidence` (default 0.3)
   - `summary`: `"Data-driven analysis (AI unavailable). Based on composite score X/100, DIRECTION signal."`
   - `risk_assessment`: `"Limited analysis — AI debate unavailable. Exercise additional caution."`

3. **`DebateResult.is_fallback = True`** — CLI renders a yellow warning banner.

---

## Prompt Design Rules

### Constants

Each agent module has an inline string constant. No template system.

```python
# VERSION: v1.0
BULL_SYSTEM_PROMPT = """You are a bullish options analyst. ..."""
```

### Requirements

- **Version header**: every prompt constant has `# VERSION: v1.0` comment above it
- **Token budget**: system prompts < 1500 tokens, context block adds ~300-500 tokens
- **Flat context**: `MarketContext` rendered as key-value text block, not JSON blob
- **Options-specific**: agents MUST cite specific strikes, expirations, Greeks, indicators
- **No hallucinated data**: agents can only reference data present in the context block
- **Rebuttal injection**: bear receives bull's text wrapped in `<<<BULL_ARGUMENT>>>` delimiters
  to prevent instruction bleed from LLM-generated text

### Context Rendering

```python
def render_context_block(ctx: MarketContext) -> str:
    """Render MarketContext as flat key-value text for agent consumption."""
    return f"""TICKER: {ctx.ticker}
PRICE: ${ctx.current_price}
52W HIGH: ${ctx.price_52w_high}
52W LOW: ${ctx.price_52w_low}
RSI(14): {ctx.rsi_14:.1f}
MACD: {ctx.macd_signal.value}
IV RANK: {ctx.iv_rank:.1f}
SECTOR: {ctx.sector}
TARGET STRIKE: ${ctx.target_strike}
TARGET DELTA: {ctx.target_delta:.2f}
DTE: {ctx.dte_target}
DIV YIELD: {ctx.dividend_yield:.2%}"""
```

---

## DebateConfig (Nested BaseModel on AppSettings)

```python
class DebateConfig(BaseModel):
    """AI debate configuration."""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: float = 90.0           # per-agent timeout (seconds)
    num_ctx: int = 8192                    # Ollama context window size
    retries: int = 2                       # PydanticAI retry count
    fallback_confidence: float = 0.3       # data-driven fallback confidence cap
    max_total_duration: float = 300.0      # total debate timeout (seconds)
```

Added to `AppSettings` as `debate: DebateConfig = DebateConfig()`.
Env override: `ARENA_DEBATE__NUM_CTX=16384` → `settings.debate.num_ctx == 16384`.

---

## Testing Patterns (Context7-Verified)

### TestModel for Unit Tests

```python
import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

# Context7-verified: prevents accidental real API calls in test suite
models.ALLOW_MODEL_REQUESTS = False

@pytest.mark.asyncio
async def test_bull_agent_produces_valid_output() -> None:
    deps = DebateDeps(context=mock_context, ticker_score=mock_score, contracts=[mock_contract])
    # Context7-verified: agent.override(model=TestModel()) as context manager
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=deps)
    assert isinstance(result.output, AgentResponse)
    assert 0.0 <= result.output.confidence <= 1.0
```

### TestModel with Custom Output

```python
# Context7-verified: custom_output_args controls structured output fields
test_model = TestModel(custom_output_args={
    "agent_name": "bull",
    "direction": "bullish",
    "confidence": 0.75,
    "argument": "Strong momentum with RSI at 65.",
    "key_points": ["RSI trending up", "Volume increasing"],
    "risks_cited": ["Earnings next week"],
    "contracts_referenced": ["AAPL 190C 2026-04-18"],
    "model_used": "test",
})
with bull_agent.override(model=test_model):
    result = await bull_agent.run("test", deps=deps)
    assert result.output.confidence == 0.75
```

### Orchestrator Tests (Mock Agents)

Test success path, partial failure, full failure, timeout, and `--fallback-only`:

```python
@pytest.mark.asyncio
async def test_debate_fallback_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Orchestrator returns fallback when Ollama is unreachable."""
    # Mock agent.run to raise httpx.ConnectError
    result = await run_debate(score, contracts, quote, info, config)
    assert result.is_fallback is True
    assert result.thesis.confidence == 0.3
```

### What NOT to Test

- Don't test actual Ollama responses in unit tests — use `TestModel`
- Don't test prompt quality (subjective) — test prompt structure (version header, token count)
- Don't test Rich rendering of debate panels — test the data transformations
- Don't assert on `RunUsage` exact token counts from `TestModel` — they're synthetic

### Integration Tests (Require Ollama)

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_debate_with_ollama() -> None:
    """Full debate with real Ollama. Skipped in CI."""
    # ... requires `ollama pull llama3.1:8b` on test machine
```

Mark with `@pytest.mark.integration`. Skipped by default; run with `pytest -m integration`.

---

## What Claude Gets Wrong — Agents-Specific (Fix These)

1. **Inter-agent imports** — `bull.py` must never import from `bear.py` or `risk.py`. Agents
   are self-contained modules. Only the orchestrator imports from all three.

2. **Fetching data in agents** — Agents and orchestrator receive all data pre-fetched.
   Never import `httpx`, `yfinance`, or service classes. The caller (CLI) provides
   `TickerScore`, `Quote`, `TickerInfo`, and `OptionContract` list.

3. **`async def` on Typer command** — The `debate` CLI command is sync + `asyncio.run()`.
   Never use `async def` on a Typer command.

4. **Forgetting `asyncio.wait_for` on agent.run()** — Every `agent.run()` call must be
   wrapped in `asyncio.wait_for(timeout=config.ollama_timeout)`. Ollama can hang indefinitely
   on CPU inference.

5. **`except Exception` without fallback** — The orchestrator must ALWAYS return a
   `DebateResult`. On any error, return the data-driven fallback. Never let an exception
   propagate to the CLI.

6. **Using `Agent(model="ollama:llama3.1:8b")`** — Don't set model at init time. Use
   `model=None` at init, pass `OllamaModel` at `agent.run(model=...)` time. This enables
   `TestModel` override in tests.

7. **Forgetting the `<think>` tag validator** — All three agents need `@agent.output_validator`
   that rejects `<think>` tags via `ModelRetry`. Llama 3.1 8B produces these frequently.

8. **`markup=True` in Rich panels** — Agent argument text may contain `[brackets]` from
   indicator names. Use `markup=False` or escape brackets in rendering code.

9. **Returning `dict` from `build_market_context()`** — Must return `MarketContext` typed model.

10. **Assuming yfinance provides Greeks** — `OptionContract.greeks` is populated by
    `pricing/dispatch.py` during the scan pipeline. Agents receive contracts with Greeks
    already computed. Never import from `pricing/`.

11. **`Optional[X]` syntax** — Use `X | None`. Never import from `typing`. Python 3.13+.

12. **Missing `models.ALLOW_MODEL_REQUESTS = False` in tests** — Without this guard, a test
    misconfiguration could accidentally make real API calls. Set at module level in every
    test file.

13. **Parallel agent execution** — Agents run sequentially (bull → bear → risk). Ollama is
    single-threaded on CPU. Don't use `asyncio.gather` for agent calls.

14. **Forgetting `dynamic=True` on bear/risk prompts** — Bear and risk prompts depend on
    runtime deps (opponent arguments). Without `dynamic=True`, the prompt is cached from the
    first run and won't include the injected arguments.

15. **`print()` in agent code** — Use `logging.getLogger(__name__)`. Only `cli/` uses `print()`.
