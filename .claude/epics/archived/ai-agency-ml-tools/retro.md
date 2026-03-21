---
name: Retro — ai-agency-ml-tools
created: 2026-03-21T15:40:00Z
---

# Retro: ai-agency-ml-tools (Epic 8)

## Effort

| Metric | Planned | Actual |
|--------|---------|--------|
| Tasks | 4 | 4 |
| Test cases | ~50 | 70 (1.4x) |
| Test files | 4 | 4 |
| Proxy hours | 15h | ~1h (single session) |
| Lines changed | — | +1,755 / -54 |
| Files changed | — | 17 |

**Ratio**: 0.07x (dramatically under estimated effort — tasks were less complex than expected)

## Scope Delta

| Planned | Delivered | Delta |
|---------|-----------|-------|
| 4 tool wrappers | 4 tool wrappers | On-target |
| Conditional registration in 5 builders | 5 builders updated | On-target |
| `<<<AVAILABLE_TOOLS>>>` prompt block | `render_available_tools()` | On-target |
| ~50 tests | 70 tests | +40% |
| — | Tool budget increases (config.py) | Unplanned but necessary |
| — | 5 existing test file updates | Unplanned but necessary |

## Quality

| Metric | Value |
|--------|-------|
| Post-merge fixes | 0 |
| Tests passing | 70/70 new, 1007/1007 agent suite |
| Lint issues | 0 |
| Type errors | 0 |
| Critical tier | 188 pass |

## Learnings

### What went well
1. **Single-session execution** — all 4 tasks completed together because they share the same file (`_toolsets.py`) and have clear patterns
2. **Existing tool patterns** — the `compute_hv_yang_zhang_tool` provided an exact template for all 4 new tools
3. **Comprehensive test infrastructure** — the existing `_make_deps()`, `_make_mock_ctx()` patterns made test writing fast

### What required adjustment
1. **Tool budget increases** — adding tools to existing desks caused `UsageLimits` violations in tests. Had to increase `default_tool_budget` 4→5, `risk_tool_budget` 5→8, `research_tool_budget` 7→13
2. **Existing test assertions** — 7 test files had hardcoded tool counts or budget values that needed updating
3. **Epic spec used `FunctionToolset` class** — actual codebase uses `list[object]` for toolsets, not PydanticAI's `FunctionToolset`. Adapted to match existing pattern.

### Estimation insight
- The 15h estimate assumed 4 separate implementation sessions with analysis phases. In practice, the tasks are simple wrappers following an established pattern — the actual complexity was low.
- Future toolset-addition epics should estimate ~1-2h per tool wrapper when the pattern is already established.
