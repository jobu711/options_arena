---
name: unified-agent-system-foundation
status: completed
created: 2026-03-21T16:31:55Z
updated: 2026-03-22T00:00:00Z
completed: 2026-03-22T00:00:00Z
progress: 100%
prd: .claude/prds/unified-agent-system.md
parent_epic: unified-agent-system
depends_on: []
github: https://github.com/jobu711/options_arena/issues/630
---

# Epic: unified-agent-system-foundation

## Overview

Create the foundation models and synthesis agent for the unified recommendation system. This epic delivers all new Pydantic models (`DomainAssessment` hierarchy with 6 subclasses, `PositionRecommendation`, `RecommendationResult`), the `SynthesisDeps` dataclass, the synthesis agent with its prompt and toolset, and model re-exports. No existing code is modified — this is purely additive.

## Scope Boundary

### In Scope
- `models/recommendation.py` — `DomainAssessment` base + 6 subclasses (`TrendAssessment`, `VolatilityAssessment`, `FlowAssessment`, `FundamentalAssessment`, `RiskDeskAssessment`, `ContrarianAssessment`), `AnyAssessment` discriminated union, `PositionRecommendation`, `RecommendationResult`
- `agents/synthesis_agent.py` — `SynthesisDeps` dataclass, `synthesis_agent: Agent[SynthesisDeps, PositionRecommendation]`, `run_synthesis()` runner
- `agents/prompts/synthesis.py` — Synthesis agent system prompt
- `agents/_toolsets.py` — `build_synthesis_toolset()` addition
- `models/__init__.py` — Re-export new models
- Unit tests for all new models and synthesis agent

### Out of Scope (handled by sibling epics)
- DeskDeps extension (desk-recommend)
- Desk recommendation agents (desk-recommend)
- Recommendation orchestrator (orchestrator)
- CLI/API wiring (cutover)
- Debate code deletion (cutover)

## Architecture Decisions

- **Discriminated union**: `AnyAssessment` uses Pydantic v2 `Discriminator("desk")` + `Tag()` for polymorphic deserialization from JSON. Each subclass narrows `desk` to `Literal[DeskType.X]`.
- **Frozen models**: All new models use `ConfigDict(frozen=True)` for immutable snapshots.
- **`arbitrary_types_allowed=True`** on `RecommendationResult` because `RunUsage` is a plain dataclass from pydantic-ai.
- **Decimal fields**: `entry_price`, `stop_loss`, `take_profit` on `PositionRecommendation` use `Decimal` with `field_serializer` to `str`.
- **Synthesis agent**: `Agent[SynthesisDeps, PositionRecommendation]` with `model=None` at init, actual model at `run()` time. `@output_validator` strips think tags. `retries=2`.
- **Synthesis toolset**: Lightweight tools for supplemental lookups (fetch_quote, fetch_option_chain_summary). Desk agents do the heavy analysis — synthesis focuses on weighing and recommending.

## Technical Approach

### Models (`models/recommendation.py`)

```python
# DomainAssessment base — frozen, desk discriminator
# 6 subclasses with domain-specific optional fields
# AnyAssessment = Annotated[Union[...], Discriminator("desk")]
# PositionRecommendation — frozen, Decimal prices, confidence validator
# RecommendationResult — frozen, arbitrary_types_allowed for RunUsage
```

Key validators:
- `confidence`: `isfinite()` + `[0.0, 1.0]`
- `position_size_pct`: `isfinite()` + `[0.0, 1.0]`
- `risk_reward_ratio`: `isfinite()` + `> 0`
- Decimal fields: `field_serializer` to `str`
- `direction`: `SignalDirection` enum

### Synthesis Agent (`agents/synthesis_agent.py`)

```python
@dataclass
class SynthesisDeps:
    context: MarketContext
    assessments: list[DomainAssessment]
    contracts: list[OptionContract]
    ticker_score: TickerScore
    learned_patterns: str = ""
    tuned_weights: str = ""

synthesis_agent: Agent[SynthesisDeps, PositionRecommendation] = Agent(
    model=None, deps_type=SynthesisDeps,
    output_type=PositionRecommendation, retries=2,
    tools=build_synthesis_toolset(),
)

async def run_synthesis(...) -> PositionRecommendation:
    # Never-raises wrapper with fallback
```

## Task Breakdown Preview

- [ ] Task 1: Create `models/recommendation.py` — DomainAssessment hierarchy + AnyAssessment union
- [ ] Task 2: Create `models/recommendation.py` — PositionRecommendation + RecommendationResult
- [ ] Task 3: Create `agents/prompts/synthesis.py` — synthesis agent system prompt
- [ ] Task 4: Add `build_synthesis_toolset()` to `agents/_toolsets.py` + create `agents/synthesis_agent.py`
- [ ] Task 5: Re-export models from `models/__init__.py`, unit tests for all new code

## Dependencies

- None — this is the first epic in the chain
- Uses existing models: `MarketContext`, `OptionContract`, `TickerScore`, `DeskType`, `SignalDirection`, `SpreadType`, `VolRegime`, `IVTermStructureShape`, `ValuationSignal`
- Uses existing: `strip_think_tags()`, `PROMPT_RULES_APPENDIX` from `_parsing.py`

## Success Criteria

- All new models construct, validate, and round-trip through JSON correctly
- `AnyAssessment` discriminated union deserializes polymorphically (each subclass preserves domain fields)
- Synthesis agent produces valid `PositionRecommendation` with `TestModel`
- `models.ALLOW_MODEL_REQUESTS = False` in all test files
- `ruff check`, `pytest`, `mypy --strict` all pass
- No existing tests broken (purely additive epic)

## Tasks Created

- [ ] #632 - DomainAssessment hierarchy + AnyAssessment discriminated union (parallel: true)
- [ ] #633 - PositionRecommendation + RecommendationResult models (parallel: false, depends: #632)
- [ ] #634 - Synthesis agent system prompt (parallel: true)
- [ ] #635 - Synthesis toolset + synthesis agent module (parallel: false, depends: #632, #633, #634)
- [ ] #636 - Model re-exports + integration tests (parallel: false, depends: #632, #633, #635)

Total tasks: 5
Parallel tasks: 2 (001, 003 can run simultaneously)
Sequential tasks: 3 (002 → 004 → 005)
Estimated total effort: 14-20 hours

## Test Coverage Plan

Total test files planned: 6
Total test cases planned: ~48

## Estimated Effort

- 5 tasks
- ~500-700 LOC new models + agent + prompt + toolset
- ~150-200 LOC new tests (15-20 test cases)
- Low risk — no existing code modified
