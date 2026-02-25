---
name: debate-expand-context
status: completed
created: 2026-02-24T21:49:24Z
updated: 2026-02-25T09:16:54Z
completed: 2026-02-25T09:16:54Z
progress: 100%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: https://github.com/jobu711/options_arena/issues/71
---

# Epic 1: Expand MarketContext with Indicators and Greeks

## Overview

Agents currently see only 3 of 14 computed indicators (RSI, IV Rank, IV Percentile) and
1 of 5 Greeks (delta). This epic expands `MarketContext` with the remaining indicators,
all Greek values, composite score, direction signal, and contract mid price. The renderer
uses conditional formatting so `None` fields are omitted from agent context text.

## Scope

### PRD Requirements Covered
FR-A1 (Indicator Summary), FR-A2 (Contract Greeks)

### The Elegant Approach

**Add individual fields with defaults** (not nested models). This maintains the proven flat
pattern, ensures backward compatibility, and keeps `render_context_block()` simple. Each
new field defaults to `None` — existing `MarketContext(...)` calls don't break.

**Dynamic rendering**: Instead of hardcoding each new line in `render_context_block()`,
use a helper that conditionally appends non-None fields:

```python
def _render_optional(label: str, value: float | None, fmt: str = ".1f") -> str | None:
    if value is not None and math.isfinite(value):
        return f"{label}: {value:{fmt}}"
    return None
```

### Deliverables

**`src/options_arena/models/analysis.py`** — Add to `MarketContext`:

```python
# Scoring context
composite_score: float = 0.0
direction_signal: SignalDirection = SignalDirection.NEUTRAL

# Indicators (normalized 0-100, None = not computed)
adx: float | None = None
sma_alignment: float | None = None
bb_width: float | None = None
atr_pct: float | None = None
stochastic_rsi: float | None = None
relative_volume: float | None = None

# Greeks beyond delta
target_gamma: float | None = None
target_theta: float | None = None
target_vega: float | None = None
target_rho: float | None = None

# Contract pricing
contract_mid: Decimal | None = None
```

Add `field_serializer` for `contract_mid`.

**`src/options_arena/agents/orchestrator.py`** — Expand `build_market_context()`:

```python
composite_score=ticker_score.composite_score,
direction_signal=ticker_score.direction,
adx=signals.adx,
sma_alignment=signals.sma_alignment,
bb_width=signals.bb_width,
atr_pct=signals.atr_pct,
stochastic_rsi=signals.stochastic_rsi,
relative_volume=signals.relative_volume,
target_gamma=first_contract.greeks.gamma if first_contract and first_contract.greeks else None,
target_theta=first_contract.greeks.theta if first_contract and first_contract.greeks else None,
target_vega=first_contract.greeks.vega if first_contract and first_contract.greeks else None,
target_rho=first_contract.greeks.rho if first_contract and first_contract.greeks else None,
contract_mid=first_contract.mid if first_contract else None,
```

**`src/options_arena/agents/_parsing.py`** — Expand `render_context_block()` with
conditional rendering of new fields. Use `_render_optional()` helper.

### Tests (~8)
- Construct `MarketContext` with all new fields populated
- Construct with all defaults (backward compat — zero args for new fields)
- `render_context_block()` includes non-None indicators, omits None
- `contract_mid` Decimal serialization round-trip
- `build_market_context()` populates new fields from `TickerScore` and `OptionContract`

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Tasks Created
- [ ] #72 - Add indicator and Greeks fields to MarketContext (parallel: false)
- [ ] #73 - Expand build_market_context() to populate new fields (parallel: true)
- [ ] #74 - Expand render_context_block() with conditional rendering (parallel: true)
- [ ] #75 - Write unit tests for expanded MarketContext (parallel: false)

Total tasks: 4
Parallel tasks: 2 (#73 + #74 can run concurrently after #72)
Sequential tasks: 2 (#72 first, #75 last)
Estimated total effort: 4-7 hours

### Dependency Graph
```
#72 (MarketContext fields)
 ├── #73 (build_market_context)  ──┐
 └── #74 (render_context_block)  ──┤
                                   └── #75 (unit tests)
```

## Dependencies
- **Blocked by**: Nothing (foundation for all other epics)
- **Blocks**: Epics 2, 4, 5, 6, 7
