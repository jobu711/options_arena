---
name: debate-bull-rebuttal
status: backlog
created: 2026-02-24T21:49:24Z
progress: 0%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 5: Bull Rebuttal Round

## Overview

The current single-pass debate gives the bear the last word before Risk synthesizes.
The bull has no chance to defend against the bear's strongest points. This epic adds an
optional rebuttal round where the bull addresses the bear's key counterarguments.

## Scope

### PRD Requirements Covered
FR-B2 (Bull Rebuttal Round)

### The Elegant Approach

**No new agent.** The existing `bull_agent` runs a second time with different deps.
Convert bull's system prompt from static to `dynamic=True` — when
`ctx.deps.bear_counter_argument` is set, the prompt switches to rebuttal mode.

**Token-efficient.** Inject only bear's `key_points` (joined as text), not the full
argument. Saves ~300 tokens per rebuttal. The rebuttal prompt instructs "address the
bear's strongest 2-3 points in 3-5 sentences."

**Minimal invasiveness.** One file's prompt changes from static to dynamic. The
orchestrator adds a conditional phase. Everything else is additive.

### Deliverables

**`src/options_arena/agents/bull.py`** — Convert to `dynamic=True`:

```python
BULL_REBUTTAL_INSTRUCTIONS = """
The bear has countered your argument with these key points:
<<<BEAR_COUNTER>>>
{bear_key_points}
<<<END_BEAR_COUNTER>>>

Provide a BRIEF rebuttal addressing the bear's strongest 2-3 points.
Do not repeat your original argument -- focus only on defending against the counter.
Keep this concise (3-5 sentences)."""

@bull_agent.system_prompt(dynamic=True)
async def bull_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    base = BULL_SYSTEM_PROMPT + PROMPT_RULES_APPENDIX
    if ctx.deps.bear_counter_argument is not None:
        base += BULL_REBUTTAL_INSTRUCTIONS.format(
            bear_key_points=ctx.deps.bear_counter_argument
        )
    return base
```

**`src/options_arena/agents/_parsing.py`** — Add:
- `bear_counter_argument: str | None = None` to `DebateDeps`
- `bull_rebuttal: AgentResponse | None = None` to `DebateResult`

**`src/options_arena/agents/orchestrator.py`** — Add rebuttal phase:

```python
# --- Bull rebuttal (opt-in) ---
rebuttal_output: AgentResponse | None = None
if config.enable_rebuttal:
    bear_key_points = "\n".join(f"- {p}" for p in bear_output.key_points)
    rebuttal_deps = DebateDeps(
        context=context, ticker_score=ticker_score, contracts=contracts,
        bear_counter_argument=bear_key_points,
    )
    rebuttal_result = await asyncio.wait_for(
        bull_agent.run(..., model=model, deps=rebuttal_deps), timeout=per_agent_timeout,
    )
    rebuttal_output = rebuttal_result.output
    total_usage = total_usage + rebuttal_result.usage()
```

Flow: Bull -> Bear -> **Bull Rebuttal** -> [Volatility] -> Risk

**`src/options_arena/agents/risk.py`** — Update dynamic prompt to inject
`<<<BULL_REBUTTAL>>>...<<<END_BULL_REBUTTAL>>>` when `ctx.deps.bull_rebuttal` is set.
(Requires adding `bull_rebuttal: AgentResponse | None = None` to `DebateDeps`.)

**`src/options_arena/cli/rendering.py`** — Add green italic Rich panel for rebuttal.

### Tests (~10)
- Bull in rebuttal mode: dynamic prompt includes `<<<BEAR_COUNTER>>>`
- Bull in initial mode: prompt does NOT include rebuttal instructions
- Orchestrator: rebuttal enabled runs 4 agents (bull, bear, bull-rebuttal, risk)
- Orchestrator: rebuttal disabled skips rebuttal phase
- Risk prompt: includes `<<<BULL_REBUTTAL>>>` when rebuttal present, omits when absent
- Rebuttal output is valid `AgentResponse` with `agent_name="bull"`
- Token savings: only `key_points` injected (not full argument)

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epics 1 (expanded context), 2 (shared appendix), 3 (config field)
- **Blocks**: Epics 6, 7

## Key Decision
Rebuttal injects bear's `key_points` only (not full `argument`). This is both more
token-efficient and more focused — the rebuttal should address specific claims, not
re-argue the entire case.
