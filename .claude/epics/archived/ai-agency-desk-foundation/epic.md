---
name: ai-agency-desk-foundation
status: complete
created: 2026-03-17T14:37:45Z
progress: 100%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 1
dependencies: []
parallelizable_with: []
github: https://github.com/jobu711/options_arena/issues/574
---

# Epic 1: Desk Foundation

## Overview

Prove the desk agent pattern with 2 desks (Volatility + Risk). Create `DeskDeps` dataclass, `FunctionToolset` builder infrastructure, base service tools, desk prompts, new models/enums, and `AgencyConfig`. This is the foundation that all other epics depend on.

## Architecture Decisions

- `DeskDeps` as `@dataclass` (matching `DebateDeps` pattern) with 7 fields: query, ticker, market_data, options_data, fred, repo, tools_used
- `Agent(model=None, deps_type=DeskDeps, output_type=str)` at module level — model at `run()` time
- `FunctionToolset` builders in `agents/_toolsets.py` — one builder per desk, returns configured toolset
- `UsageLimits(tool_calls_limit=N)` at `run()` time — 3 for vol, 5 for risk
- Base tools only in this epic — analysis/ML tools added in Epics 7-8
- Desk prompts in `agents/prompts/desk_*.py` — shorter (~2000 chars), conversational, no `PROMPT_RULES_APPENDIX`
- `<think>` tag stripping via post-`run()` helper (no `@output_validator` needed for `str` output)

## Technical Approach

### New Models & Enums (in `models/`)
- `DeskType` StrEnum (7 members: trend, volatility, flow, fundamental, risk, contrarian, research)
- `QueryType` StrEnum (5 members: analysis, comparison, strategy, risk_check, general)
- `QueryIntent` frozen model (desks, query_type, tickers)
- `DeskResponse` frozen model (desk, response, tools_used, confidence with validators)
- `AgencyConfig` BaseModel nested on `AppSettings` (agent_timeout, default tool budgets)

### New Agent Files
- `agents/volatility_desk.py` — `vol_desk: Agent[DeskDeps, str]` with dynamic system prompt
- `agents/risk_desk.py` — `risk_desk: Agent[DeskDeps, str]` with dynamic system prompt
- `agents/_toolsets.py` — `build_volatility_toolset()`, `build_risk_toolset()` returning `FunctionToolset`

### Base Tool Wrappers (in `_toolsets.py`)
- `fetch_quote` — wraps `MarketDataService.fetch_quote()`
- `fetch_vol_surface_slice` — wraps `OptionsDataService` vol surface methods
- `fetch_iv_for_strike` — wraps IV computation
- `fetch_correlation` — wraps correlation data fetch
- `fetch_portfolio_exposure` — wraps Repository portfolio queries
- All tools return formatted strings, never raise, append to `ctx.deps.tools_used`

### Desk Prompts
- `agents/prompts/desk_volatility.py` — `DESK_VOLATILITY_PROMPT` constant
- `agents/prompts/desk_risk.py` — `DESK_RISK_PROMPT` constant

## Task Breakdown Preview

- [x] New models, enums, config (DeskType, QueryType, DeskResponse, AgencyConfig)
- [x] DeskDeps dataclass + base tool wrappers in _toolsets.py
- [x] Volatility desk agent + prompt + tests
- [x] Risk desk agent + prompt + tests

## Dependencies

- None — this is the foundation epic

## Success Criteria

- Vol and Risk desks respond to natural language queries via `TestModel`
- Tools are called and `tools_used` accumulator works
- `UsageLimits` enforces budget (3 for vol, 5 for risk)
- All existing 26,516 tests continue passing
- ~30+ new tests

## Tasks Created
- [x] #575 - Agency Models, Enums, and Config (parallel: true)
- [x] #576 - DeskDeps Dataclass and Base Tool Wrappers (parallel: true)
- [x] #577 - Volatility Desk Agent + Prompt + Tests (parallel: false, depends: #575, #576)
- [x] #578 - Risk Desk Agent + Prompt + Tests (parallel: false, depends: #575, #576)

Total tasks: 4
Parallel tasks: 2 (#575, #576)
Sequential tasks: 2 (#577, #578 — after #575+#576, but conflict on __init__.py)
Estimated total effort: ~18 hours

## Test Coverage Plan
Total test files planned: 5
Total test cases planned: ~65

## Estimated Effort

4 issues, ~2-3 implementation sessions
