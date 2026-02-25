---
name: debate-pre-screening
status: backlog
created: 2026-02-24T21:49:24Z
progress: 0%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: https://github.com/jobu711/options_arena/issues/82
---

# Epic 3: Pre-Debate Screening and Config Expansion

## Overview

The debate system currently runs AI agents on every ticker regardless of signal strength.
NEUTRAL tickers or low composite scores produce meaningless debates that waste compute
(60-90s of Ollama CPU time). This epic adds a pure-function gate and three new config
fields for the features in Epics 4 and 5.

## Scope

### PRD Requirements Covered
FR-B3 (Pre-Debate Screening), plus config fields for FR-B1 and FR-B2

### The Elegant Approach

**One pure function.** `should_debate()` takes `TickerScore` and `DebateConfig`, returns
`bool`. Called at the top of `run_debate()`. When `False`, returns a fallback result
immediately — no AI, no timeout, < 1ms.

**Config expansion in one shot.** Add all three Phase B config fields now so Epics 4 and
5 don't need to touch `config.py` independently (avoiding merge conflicts).

### Deliverables

**`src/options_arena/models/config.py`** — Add to `DebateConfig`:

```python
min_debate_score: float = 30.0        # Skip debate below this composite score
enable_volatility_agent: bool = False  # Opt-in: activate volatility agent (Epic 4)
enable_rebuttal: bool = False          # Opt-in: activate bull rebuttal round (Epic 5)
```

Validators:
- `min_debate_score`: `>= 0.0`, `<= 100.0`, `math.isfinite()`
- `enable_volatility_agent`: no validator needed (bool)
- `enable_rebuttal`: no validator needed (bool)

**`src/options_arena/agents/orchestrator.py`** — Add:

```python
def should_debate(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return False if signal is too weak for meaningful AI debate."""
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    if ticker_score.composite_score < config.min_debate_score:
        return False
    return True
```

Call at top of `run_debate()`:

```python
if not should_debate(ticker_score, config):
    logger.info("Skipping debate for %s: signal too weak", ticker_score.ticker)
    return _build_screening_fallback(context, ticker_score, contracts, config, start_time)
```

`_build_screening_fallback()` is a thin wrapper around `_build_fallback_result()` with
a custom summary: `"Signal too weak for meaningful debate (composite: X/100, direction: neutral)."`.

### Tests (~8)
- `should_debate()` returns `False` for NEUTRAL direction
- `should_debate()` returns `False` for score below threshold
- `should_debate()` returns `True` for BULLISH + score above threshold
- Edge: score exactly at `min_debate_score` returns `True` (inclusive)
- Edge: score `0.0` with non-NEUTRAL direction returns `False`
- `DebateConfig` validator rejects `min_debate_score` > 100, < 0, NaN, Inf
- Env var override: `ARENA_DEBATE__MIN_DEBATE_SCORE=50.0`
- Env var override: `ARENA_DEBATE__ENABLE_VOLATILITY_AGENT=true`

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Tasks Created
- [ ] #83 - Add pre-screening and future-feature config fields to DebateConfig (parallel: false)
- [ ] #84 - Implement should_debate() gate and screening fallback in orchestrator (parallel: false)
- [ ] #85 - Write tests for pre-screening gate and config expansion (parallel: false)

Total tasks: 3
Parallel tasks: 0
Sequential tasks: 3 (#83 -> #84 -> #85)
Estimated total effort: 5 hours

### Dependency Graph
```
#83 (DebateConfig fields)
 └── #84 (should_debate + wire into run_debate)
      └── #85 (unit tests)
```

## Dependencies
- **Blocked by**: Nothing (independent of Epic 1)
- **Blocks**: Epics 4, 5 (config fields consumed by vol agent and rebuttal)
