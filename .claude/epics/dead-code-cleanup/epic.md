---
name: dead-code-cleanup
status: backlog
created: 2026-03-23T13:21:12Z
progress: 0%
prd: .claude/prds/dead-code-cleanup.md
type: parent
child_epics:
  - dead-code-cleanup-quickwins
  - dead-code-cleanup-refactor
  - dead-code-cleanup-orphans
  - dead-code-cleanup-sunset
github: null
---

# Epic: dead-code-cleanup (Parent)

## Overview

Remove ~4,300 lines of dead, redundant, and speculative code identified by 2 forensic
audits (12 parallel agents). Pure cleanup — no behavioral changes. Organized into 4
child epics executed in parallel via git worktrees, merged sequentially.

## Architecture Decisions

- **Worktree-based parallelism**: 4 worktrees, 4 branches, 4 Claude Code sessions
- **Sequential merge order**: quickwins → refactor → orphans → sunset (resolves shared file conflicts)
- **Backward compat preserved**: `DebateResult`, `export_debate_markdown()`, old debate sub-renderers retained until Wave 4 sunset
- **Confirmed KEEP items**: backtesting (7/7 endpoints active), DSE scores (active), strategy mining (active), model routing (gated), CBOE provider (clean abstraction), analysis/ module (4 functions have callers)

## Child Epic Summary

| Epic | Scope | Worktree | Branch | Est. Tasks |
|------|-------|----------|--------|------------|
| dead-code-cleanup-quickwins | Wave 1: Delete dead functions, models, fields, types, fixtures | `../wt-quickwins/` | `epic/dead-code-cleanup-quickwins` | ~10 |
| dead-code-cleanup-refactor | Wave 2: Delete dead renderers, extract shared helpers, simplify | `../wt-refactor/` | `epic/dead-code-cleanup-refactor` | ~7 |
| dead-code-cleanup-orphans | Wave 3: Remove orphaned infrastructure, dead endpoints, eval harness | `../wt-orphans/` | `epic/dead-code-cleanup-orphans` | ~6 |
| dead-code-cleanup-sunset | Wave 4: Refactor phase_options, sunset old debate compat | `../wt-sunset/` | `epic/dead-code-cleanup-sunset` | ~4 |

## Dependency Graph

```
All 4 epics execute in parallel (git worktrees).
Merge sequentially to resolve shared-file conflicts:

quickwins ──┐
refactor  ──┤── merge to master (in order)
orphans   ──┤
sunset    ──┘
```

## Shared File Overlap Map

| File | quickwins | refactor | orphans | sunset |
|------|-----------|----------|---------|--------|
| `models/config.py` | del `num_ctx` | `FiniteFieldsMixin` | del `IntelligenceConfig`, `EvalConfig` | — |
| `models/analysis.py` | del `ContractConstraint` | `enrichment_ratio` | — | sunset thesis classes |
| `agents/__init__.py` | del dead re-exports | del renderer re-exports | — | — |
| `data/_eval.py` | del singular method | — | del entire file | — |
| `models/__init__.py` | del model re-exports | — | del eval/intel re-exports | — |

Conflicts are small (re-export lines, field deletions) and resolve trivially during sequential merge.

## Success Criteria (Technical)

- >= 3,500 lines removed across all 4 epics
- >= 20 test files updated/removed
- >= 25 dead `__init__.py` re-exports removed
- >= 14 dead API endpoints removed
- CI suite green after each epic merge
- Zero new bugs introduced

## Estimated Effort

- Total: ~27 tasks across 4 epics
- Critical path: sequential merge order (quickwins first)
- Wall-clock: ~2-3 hours with 4 parallel sessions
