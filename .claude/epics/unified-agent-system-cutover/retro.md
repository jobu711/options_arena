# Retrospective: unified-agent-system-cutover

**Date**: 2026-03-22
**Duration**: ~2.5 hours wall clock (first commit 15:23, last 17:27)

## Effort Analysis

| Task | Issue | Planned Hours | Proxy Hours | Ratio |
|------|-------|--------------|-------------|-------|
| DebateConfig cleanup | #664 | 2-3 | 0.3 | 0.1x |
| agents exports update | #666 | 1-2 | 0.3 | 0.2x |
| recommendation export | #668 | 2-3 | 0.3 | 0.1x |
| CLI rewrite | #665 | 5-7 | 0.5 | 0.1x |
| API routes rewrite | #670 | 5-7 | 0.5 | 0.1x |
| regression tests | #667 | 4-5 | 0.3 | 0.1x |
| file deletion | #669 | 3-4 | 0.3 | 0.1x |
| final cleanup | #671 | 4-6 | 1.2 | 0.2x |
| **Total** | | **28-39** | **~3.7** | **0.1x** |

**Note**: Proxy hours are from git commit timestamps and represent agent compute time. Actual elapsed wall-clock was ~2.5 hours due to parallel execution.

## Scope Delta

### Planned vs Delivered
- **Planned**: 8 tasks, ~600-800 LOC modified, ~1,200 LOC deleted, ~400-600 LOC test changes
- **Delivered**: 8 tasks, 103 files changed, +5,628/-13,191 lines (net -7,563)
- **Scope expansion**: File deletion cascaded to 24 test files (vs estimated ~9), 10 test files needed import fixes. CLAUDE.md updates were more extensive than planned.

### Unplanned Work
- #665 worktree nesting issue — had to cherry-pick commit from dangling worktree
- #670 worktree data loss — agent didn't commit, worktree auto-cleaned. Re-ran without worktree.
- #671 had to fix 35 broken test files (vs estimated ~9 in epic) — the cascade was larger than anticipated

## Quality Assessment

- **Lint**: ruff clean (0 violations)
- **Types**: mypy --strict clean (164 source files)
- **Tests**: 27,156 passed, 2 branch-introduced meta-test failures, 40 pre-existing
- **New tests**: ~239 added
- **Tests deleted**: 24 files (~7,400 lines)
- **Net code**: -7,563 lines (significant debt reduction)

## Learnings

### What Went Well
1. **Parallel Wave execution** worked perfectly for independent tasks (Wave 1: 3 agents, Wave 2: 2 agents)
2. **Test-first approach** (write regression tests before deleting) caught import issues early
3. **Grep-before-delete safety protocol** prevented broken imports in production code
4. **Factory pattern** in tests/factories.py made test data construction reusable across files

### What Didn't Go Well
1. **Worktree data loss**: Agent #670 completed work but didn't commit → worktree auto-cleaned → had to redo. Lesson: agents in worktrees MUST commit or changes are lost.
2. **Worktree nesting**: Agent #665 created a nested worktree inside a cleaned-up worktree path. CWD got stuck in the nested path.
3. **Test cascade underestimated**: Epic estimated 50-80 test changes, actual was 24 deleted + 10 fixed + 239 new = ~273 test-related changes.

### Process Improvements
- **Prefer non-worktree agents** for tasks that modify the main repo — avoids worktree cleanup/nesting issues
- **Require explicit `git commit` instructions** in agent prompts — agents don't always commit by default
- **Estimate test cascades better** — file deletion affects more test files than expected (3-4x multiplier)
