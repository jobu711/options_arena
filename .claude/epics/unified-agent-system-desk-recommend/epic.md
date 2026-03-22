---
name: unified-agent-system-desk-recommend
status: backlog
created: 2026-03-21T16:31:55Z
progress: 0%
prd: .claude/prds/unified-agent-system.md
parent_epic: unified-agent-system
depends_on:
  - unified-agent-system-foundation
github: https://github.com/jobu711/options_arena/issues/639
---

# Epic: unified-agent-system-desk-recommend

## Overview

Add recommendation mode to all 6 domain desk agents. Each desk file gains a second `Agent[DeskDeps, *Assessment]` instance that produces a structured `DomainAssessment` subclass. The existing interactive `Agent[DeskDeps, str]` instances are completely untouched. Also extends `DeskDeps` with optional scan data fields and creates 6 recommendation prompts.

## Scope Boundary

### In Scope
- Extend `DeskDeps` with 3 optional fields: `ticker_score`, `contracts`, `market_context`
- Verify/fix `DeskDeps` field ordering (non-defaults before defaults)
- Update all `DeskDeps(` call sites if needed (37 sites: 1 source + 36 tests)
- Add `build_cleaned_domain_assessment()` helper to `_parsing.py`
- Create 6 recommendation prompts: `recommend_trend.py`, `recommend_volatility.py`, `recommend_flow.py`, `recommend_fundamental.py`, `recommend_risk.py`, `recommend_contrarian.py`
- Add recommendation agent + runner to 6 desk files: `volatility_desk.py`, `risk_desk.py`, `trend_desk.py`, `flow_desk.py`, `fundamental_desk.py`, `contrarian_desk.py`
- Unit tests for each desk's recommendation mode

### Out of Scope (handled by sibling epics)
- Foundation models (foundation — already done)
- Recommendation orchestrator (orchestrator)
- CLI/API wiring (cutover)
- Research desk — excluded from recommendation mode per PRD

## Architecture Decisions

- **Dual-instance pattern**: Each desk file gains `*_desk_recommend: Agent[DeskDeps, *Assessment]` alongside existing `*_desk: Agent[DeskDeps, str]`. Both share same toolset via `build_*_toolset()`.
- **Recommendation prompts**: Use `PROMPT_RULES_APPENDIX` (unlike interactive desk prompts). Focus on structured analysis rather than conversational Q&A.
- **Output validator**: `@agent.output_validator` on recommendation agents delegates to `build_cleaned_domain_assessment()` for think-tag stripping + validation.
- **Runner pattern**: `run_*_desk_recommendation()` follows same never-raises pattern as `run_*_desk_query()`. Returns `DomainAssessment` subclass on success, fallback assessment on failure.
- **DeskDeps extension**: 3 new optional fields with defaults — backward-compatible. Interactive callers pass defaults. Recommendation orchestrator populates all three.

## Technical Approach

### DeskDeps Extension (`_desk_deps.py`)

```python
@dataclass
class DeskDeps:
    # Existing fields (verify ordering is valid)
    query: str
    ticker: str
    market_data: MarketDataService
    options_data: OptionsDataService
    repo: Repository
    fred: FredService | None = None
    tools_used: list[str] = field(default_factory=list)
    learned_patterns: str = ""
    # NEW — optional scan data for recommendation mode
    ticker_score: TickerScore | None = None
    contracts: list[OptionContract] = field(default_factory=list)
    market_context: MarketContext | None = None
```

### Per-Desk Recommendation Agent (6 desks)

Each desk file (e.g., `volatility_desk.py`) gains:
1. Import of corresponding `*Assessment` from `models/recommendation`
2. Import of recommendation prompt from `prompts/recommend_*.py`
3. New agent instance: `vol_desk_recommend: Agent[DeskDeps, VolatilityAssessment]`
4. `@vol_desk_recommend.system_prompt(dynamic=True)` for learned patterns injection
5. `@vol_desk_recommend.output_validator` for think-tag stripping
6. `run_vol_desk_recommendation(deps, model, settings, config) -> VolatilityAssessment` runner

### Cleaning Helper (`_parsing.py`)

```python
def build_cleaned_domain_assessment(text: str) -> str:
    """Strip think tags from domain assessment output."""
    # Follows build_cleaned_agent_response() pattern
```

## Tasks Created

- [ ] #640 - Extend DeskDeps with optional scan data fields (parallel: true)
- [ ] #641 - Add build_cleaned_domain_assessment to _parsing.py (parallel: true)
- [ ] #642 - Create 6 recommendation prompts (parallel: true)
- [ ] #643 - Trend + Volatility desk recommendation agents (parallel: true, depends: #640, #641, #642)
- [ ] #644 - Flow + Fundamental desk recommendation agents (parallel: true, depends: #640, #641, #642)
- [ ] #645 - Risk + Contrarian desk recommendation agents (parallel: true, depends: #640, #641, #642)

Total tasks: 6
Parallel tasks: 6 (Wave 1: #640-#642 simultaneous; Wave 2: #643-#645 simultaneous)
Sequential tasks: 0
Estimated total effort: 16-22 hours

## Test Coverage Plan

Total test files planned: 9
Total test cases planned: ~56

## Dependencies

- **unified-agent-system-foundation**: `DomainAssessment` subclasses must exist as output types
- Uses existing: `build_*_toolset()` from `_toolsets.py`, `strip_think_tags()` from `_parsing.py`
- Uses existing: `PROMPT_RULES_APPENDIX` for recommendation prompts

## Success Criteria

- Each of 6 desks has a working recommendation agent producing correct `DomainAssessment` subclass
- Interactive desk agents (`Agent[DeskDeps, str]`) completely unchanged — all existing desk tests pass
- `DeskDeps` extension is backward-compatible — all 37 construction sites work
- Recommendation prompts are < 8000 chars each, use `PROMPT_RULES_APPENDIX`
- `ruff check`, `pytest`, `mypy --strict` all pass

## Estimated Effort

- 6 tasks
- ~600-900 LOC new (6 prompts + 6 agent additions + DeskDeps extension + cleaner)
- ~200-300 LOC new tests (18-24 test cases, 3-4 per desk)
- Medium risk — modifying `DeskDeps` touches 37 call sites, but changes are additive (new optional fields)
