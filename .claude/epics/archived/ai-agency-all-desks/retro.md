---
epic: ai-agency-all-desks
completed_at: 2026-03-19T15:45:00Z
---

# Retrospective: ai-agency-all-desks (Epic 3: All Desks Online)

## Scope

**Planned**: 5 tasks, 16-24 hours estimated
**Delivered**: 5 tasks, all acceptance criteria met

| Task | Planned | Delivered | Delta |
|------|---------|-----------|-------|
| #587 Trend + Flow desks | M (4-6h) | 40 tests, 4 tools, 2 agents, 2 prompts | On scope |
| #588 Fundamental + Contrarian | M (4-6h) | 43 tests, 3 tools, 2 agents, 2 prompts, config change | On scope |
| #589 Research desk | S (2-3h) | 21 tests, 1 builder, 1 agent, 1 prompt | On scope |
| #590 Routing + integration | M (3-4h) | 27 tests, routing wiring, 7-desk integration | On scope |
| #591 Frontend DeskSelector | M (3-5h) | Vue component, page, types, route, nav link | On scope |

## Effort

**Proxy hours** (first commit to last): ~0.5h wall-clock (agents ran in parallel)
**Actual agent execution**: ~40 min total across all agents
**Estimated**: 16-24 hours manual
**Ratio**: ~0.04x (agent parallelism dramatically reduced wall-clock time)

## Quality

- **Tests**: 130 new test functions, 867 total agents suite passing
- **Post-verification fixes**: 1 (missing prompt re-exports in `prompts/__init__.py`)
- **Regressions**: 0
- **Pattern compliance**: 14/14 requirements verified PASS
- **Frontend build**: clean (`vue-tsc` + `vite`)

## Code Metrics

- **32 files changed**: 3,287 insertions, 29 deletions
- **New files**: 17 (5 agents, 5 prompts, 5 test files, 1 integration test, 1 frontend component + page + types)
- **Modified files**: 5 (`_toolsets.py`, `_routing.py`, `__init__.py`, `prompts/__init__.py`, `config.py`)

## What Went Well

1. **Worktree parallelism**: Issues #587 and #588 ran simultaneously in isolated worktrees. Merge conflicts were predictable (both added to `_toolsets.py`) and resolved cleanly.
2. **Pattern replication**: The vol_desk/risk_desk pattern from Epic 1 made it trivial for agents to replicate. Every new desk follows the exact same structure.
3. **Dependency-ordered waves**: 4-wave execution (parallel→sequential→sequential→sequential) respected the dependency graph perfectly.
4. **Verification caught a real issue**: Missing prompt re-exports would have been a production bug for any consumer importing from the prompts package.

## What Could Be Improved

1. **Agents should commit their own work**: The #591 frontend agent completed but didn't commit — had to be committed manually. Need to ensure agents always commit before returning.
2. **Task status tracking**: Task files remained `status: open` despite work being complete. Should auto-close tasks as agents finish.
3. **Prompt re-export consistency**: Both agents (#587, #588) added prompts but only one pattern (the one from #587 that was merged first) was picked up by the existing `prompts/__init__.py`. The #588 agent added its re-exports but they got lost in the merge conflict resolution.

## Learnings

- **Worktree isolation is essential** for tasks that modify the same file (`_toolsets.py`). Without it, agents would overwrite each other's changes.
- **Merge conflict resolution is a coordination tax** — 3 files needed manual resolution. Consider having a single agent handle both #587 and #588 if the shared file surface is high.
- **6 tools with budget 5 for Research desk** — the `call_tools=[]` TestModel workaround is needed to prevent test failures where TestModel tries to call all tools. Document this pattern.
