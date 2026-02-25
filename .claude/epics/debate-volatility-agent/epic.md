---
name: debate-volatility-agent
status: completed
created: 2026-02-24T21:49:24Z
completed: 2026-02-25T12:08:56Z
progress: 100%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: https://github.com/jobu711/options_arena/issues/86
---

# Epic 4: Volatility Agent with VolatilityThesis

## Overview

The debate system is purely directional — when IV Rank is 85+ the correct trade is often
non-directional (iron condor, short strangle), but the system forces every analysis into
bull-vs-bear. This epic adds a Volatility Agent that assesses whether IV is mispriced and
recommends vol-specific strategies via a structured `VolatilityThesis` output.

## Scope

### PRD Requirements Covered
FR-B1 (Volatility Agent with VolatilityThesis)

### The Elegant Approach

**New model, not reused `AgentResponse`.** `VolatilityThesis` has domain-specific fields
(`iv_assessment`, `target_iv_entry/exit`, `suggested_strikes`) that don't fit the generic
`AgentResponse` shape. Frozen, confidence-validated, same patterns as `TradeThesis`.

**Reuse shared helpers.** The output validator uses `strip_think_tags()` from `_parsing.py`
(no new cleanup code). The agent uses the same `PROMPT_RULES_APPENDIX` from Epic 2.

**Conditional orchestrator phase.** Guarded by `config.enable_volatility_agent`. When
disabled (default), the orchestrator flow is unchanged — zero overhead.

### Deliverables

**`src/options_arena/models/analysis.py`** — New model:

```python
class VolatilityThesis(BaseModel):
    """Structured output from the Volatility Agent."""
    model_config = ConfigDict(frozen=True)

    iv_assessment: str               # "overpriced", "underpriced", "fair"
    iv_rank_interpretation: str      # Human-readable IV rank context
    confidence: float                # 0.0 to 1.0
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str
    target_iv_entry: float | None = None
    target_iv_exit: float | None = None
    suggested_strikes: list[str]
    key_vol_factors: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v
```

**`src/options_arena/models/__init__.py`** — Re-export `VolatilityThesis`.

**`src/options_arena/agents/volatility.py`** — New agent (~100 lines):

```python
volatility_agent: Agent[DebateDeps, VolatilityThesis] = Agent(
    model=None, deps_type=DebateDeps, output_type=VolatilityThesis, retries=2,
)
```

- `dynamic=True` system prompt: injects bull + bear arguments when available
- Uses `PROMPT_RULES_APPENDIX` from `_parsing.py` (shared with other agents)
- Output validator: strips `<think>` tags from string fields via new
  `build_cleaned_volatility_thesis()` in `_parsing.py`
- Prompt focuses on: IV Rank, IV Percentile, ATM IV 30D, historical vol context

**`src/options_arena/agents/_parsing.py`** — Add:
- `vol_response: VolatilityThesis | None = None` to `DebateDeps`
- `vol_response: VolatilityThesis | None = None` to `DebateResult`
- `build_cleaned_volatility_thesis()` helper

**`src/options_arena/agents/orchestrator.py`** — Add volatility phase:

```python
# --- Volatility agent (opt-in) ---
vol_output: VolatilityThesis | None = None
if config.enable_volatility_agent:
    vol_deps = DebateDeps(
        context=context, ticker_score=ticker_score, contracts=contracts,
        bull_response=bull_output, bear_response=bear_output,
    )
    vol_result = await asyncio.wait_for(
        volatility_agent.run(..., model=model, deps=vol_deps), timeout=per_agent_timeout,
    )
    vol_output = vol_result.output
    total_usage = total_usage + vol_result.usage()
```

**`src/options_arena/agents/risk.py`** — Update dynamic prompt to inject
`<<<VOL_CASE>>>...<<<END_VOL_CASE>>>` when `ctx.deps.vol_response` is present.

**`src/options_arena/agents/__init__.py`** — Re-export `volatility_agent`.

**`src/options_arena/cli/rendering.py`** — Add cyan-bordered Rich panel for vol output.

### Tests (~14)
- `VolatilityThesis` model: construction, frozen, confidence validation, JSON round-trip
- Volatility agent with `TestModel`: valid output, think-tag stripping
- Orchestrator: vol enabled produces 4-agent flow, vol disabled skips phase
- Risk prompt: includes `<<<VOL_CASE>>>` when vol present, omits when absent
- CLI rendering: vol panel appears when `vol_response` is set

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epics 1 (expanded context), 2 (shared prompt appendix + validator helper), 3 (config fields)
- **Blocks**: Epics 5 (rebuttal slot ordering), 6, 7

## Key Decision
Flow order: Bull -> Bear -> **Volatility** -> Risk. Volatility runs after Bear because it
can reference both directional arguments. Risk runs last because it synthesizes everything.

## Tasks Created
- [ ] #87 - Add VolatilityThesis model and re-export (parallel: true)
- [ ] #89 - Update DebateDeps, DebateResult, and add parsing helper (depends: #87)
- [ ] #91 - Implement Volatility Agent (depends: #87, #89)
- [ ] #88 - Integrate Volatility Agent into orchestrator and update Risk agent (depends: #89, #91)
- [ ] #90 - Add CLI rendering for volatility output (parallel: true, depends: #87)
- [ ] #92 - Write comprehensive tests for Volatility Agent feature (depends: all)

Total tasks: 6
Parallel tasks: 2 (#87, #90 can run concurrently)
Sequential tasks: 4 (#89 -> #91 -> #88 -> #92)
Estimated total effort: 17 hours
