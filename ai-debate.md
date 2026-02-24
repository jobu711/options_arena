# AI Debate System — PRD Brief

## What To Build

A three-agent AI debate system for Options Arena where Bull, Bear, and Risk agents
argue over individual option contracts and produce a structured `TradeThesis` verdict.
Backend-only (Phase 9). Web UI and streaming come later (Phase 11).

## Why It Matters

The AI debate is Options Arena's moat — no competitor does local AI-powered multi-agent
options analysis. V1's scan pipeline scores and recommends contracts quantitatively.
The debate adds qualitative reasoning: *why* a contract is attractive, what could go wrong,
and a synthesized risk assessment. Users get conviction, not just a number.

## Existing Infrastructure (Already Built)

### Models (`src/options_arena/models/analysis.py` — 220+ tests)
- **`MarketContext`**: Flat snapshot of ticker state passed to all agents. Fields: ticker,
  price, Greeks (via `OptionGreeks`), indicator signals, sector, dividend_yield, exercise_style.
  Intentionally flat — LLMs parse key-value pairs better than nested JSON.
- **`AgentResponse`**: Structured output from bull/bear agents. Fields: agent_name, position
  (BULLISH/BEARISH/NEUTRAL), reasoning, contracts_cited, confidence (validated [0,1]),
  key_risks, catalysts. Frozen model.
- **`TradeThesis`**: Final verdict from risk agent. Fields: ticker, direction, confidence,
  primary_rationale, bull_case_summary, bear_case_summary, risk_factors,
  recommended_action, position_sizing_note. Frozen model.

### Database (`data/migrations/001_initial.sql`)
- `ai_theses` table exists but is unused — ready for debate persistence.

### Scan Pipeline Output
- `TickerScore` with composite_score, direction (BULLISH/BEARISH/NEUTRAL), raw + normalized
  `IndicatorSignals`, and recommended `OptionContract` list (with Greeks computed via
  `pricing/dispatch.py`).

### PydanticAI Pattern (Proven in v3 migration, ~300 lines removed)
- Module-level `Agent[Deps, OutputType]` instances (not classes)
- `@dataclass` deps injected at `agent.run(..., deps=deps, model=model)`
- `output_type=PydanticModel` enforces structured JSON from LLM
- `retries=2` for automatic retry on validation failure
- `model_settings=ModelSettings(extra_body={"num_ctx": 8192})` for Ollama context window
- `@agent.output_validator` rejects `<think>` tag remnants, triggers `ModelRetry`
- `@agent.system_prompt` decorator for static prompt constants
- `TestModel` for unit tests (no real Ollama needed)

## Debate Flow

```
1. Caller provides: TickerScore + live Quote + TickerInfo
2. Build MarketContext (flat snapshot of all relevant data)
3. Bull agent: argue bullish case → AgentResponse
4. Bear agent: receive bull's argument + context, argue bearish → AgentResponse
5. Risk agent: receive both arguments + context, synthesize → TradeThesis
6. Persist debate to ai_theses table
7. Return DebateResult (context + all responses + verdict + RunUsage metadata)
```

Single-pass only (no multi-round rebuttal). ~60-90s on CPU with Llama 3.1 8B.

## Technical Requirements

### Agent Framework
- **PydanticAI** (`pydantic-ai >= 1.62.0`) — already a project dependency
- **Ollama** (`ollama >= 0.6.1`) — local Llama 3.1 8B, already a dependency
- Host resolution: explicit arg > `OLLAMA_HOST` env var > `localhost:11434`

### Files To Create
| File | Purpose |
|------|---------|
| `agents/__init__.py` | Re-exports with `__all__` |
| `agents/model_config.py` | `build_ollama_model()`, host resolution |
| `agents/bull.py` | `Agent[DebateDeps, AgentResponse]` — bullish thesis |
| `agents/bear.py` | `Agent[DebateDeps, AgentResponse]` — bearish counter |
| `agents/risk.py` | `Agent[DebateDeps, TradeThesis]` — synthesized verdict |
| `agents/_parsing.py` | Shared models (`DebateDeps` dataclass), constants, validators |
| `agents/orchestrator.py` | Single-pass coordinator, error handling, fallback |
| `agents/prompts/templates/*.txt` | Prompt templates for each agent |

### Files To Modify
| File | Change |
|------|--------|
| `data/repository.py` | Add `save_debate()`, `get_debates_for_ticker()` |
| `cli/commands.py` | Add `debate` command |
| `models/config.py` | Add `DebateConfig` nested model (timeout, retries, model name) |

### Architecture Boundaries
- `agents/` CAN access: `models/`, `services/` output, `pydantic_ai`
- `agents/` CANNOT access: other agents directly, `indicators/`, APIs, `pricing/`
- Agents have no knowledge of each other — the orchestrator coordinates them
- All external calls need `asyncio.wait_for(timeout=N)`

### Error Handling & Fallback
- Orchestrator catches `UnexpectedModelBehavior`, timeout, connection errors
- **Data-driven fallback**: when Ollama is unreachable, synthesize a verdict from
  quantitative data (composite score, direction, indicator signals, Greeks) without
  LLM reasoning. Verdict confidence reduced to reflect lack of qualitative analysis.
- `RunUsage` accumulation: `bull_usage + bear_usage + risk_usage` for token tracking
- FRED-style "never raises" pattern: debate failure returns fallback, never crashes scan

### Prompt Requirements
- Versioned: every template has `# VERSION: v1.0` header
- Flat context blocks (key-value pairs, not JSON blobs)
- Options-specific: agents MUST cite specific strikes, expirations, Greeks, indicators
- Rebuttal injection: opponent's text wrapped in delimiters to prevent instruction bleed
- Token budget: system prompts < 1500 tokens, context adds 300-500 tokens
- No hallucinated data: agents can only reference data present in `MarketContext`

### Persistence
- Save full debate to `ai_theses` table after completion
- Fields: ticker, scan_run_id, bull response JSON, bear response JSON, thesis JSON,
  total tokens used, model name, duration_ms, created_at (UTC)
- Query: `get_debates_for_ticker(ticker, limit)` returns most recent debates

### CLI Integration
- `options-arena debate AAPL` — run debate on single ticker
- Requires: recent scan run with scored data for the ticker
- Output: Rich-formatted bull/bear/risk panels + verdict card
- `--fallback-only` flag to test data-driven path without Ollama

### Testing
- ~80-100 tests using PydanticAI `TestModel` (no real Ollama)
- Test each agent independently with known `MarketContext` inputs
- Test orchestrator with mock agents (success, timeout, Ollama down)
- Test data-driven fallback produces valid `TradeThesis`
- Test persistence round-trip (save + retrieve)
- Test CLI output rendering
- Integration test: full debate with Ollama running (marked `@pytest.mark.integration`)

## What's NOT In Scope

- Multi-round rebuttal (single-pass only)
- Additional LLM providers beyond Ollama (defer to v2.1)
- Web UI for debate (Phase 11, separate PRD)
- SSE streaming of agent progress (Phase 11)
- Automated debate triggers (manual CLI/web only)
- Strategy builder / multi-leg analysis (V3)

## Success Criteria

- `options-arena debate AAPL` completes in < 120s on CPU
- Data-driven fallback produces valid thesis when Ollama is down
- All three agents cite specific contracts, strikes, and Greeks from `MarketContext`
- `ai_theses` table populated with full debate transcript
- `TestModel` tests pass without Ollama installed
- ruff + pytest + mypy --strict all green
- Zero architecture boundary violations
