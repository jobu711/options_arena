---
epic: volatility-intelligence
retro_date: 2026-03-14T15:50:00Z
---

# Retrospective: volatility-intelligence

## Scope

### Planned
- 5 issues (#500-#504) across 3 waves
- 1 new file, ~9 modified files, ~80 new tests
- Critical path: #500 → #501 → #503 → #504 (4 sequential steps)
- Parallel: #500 and #502 (Wave 1)

### Delivered
- 5 issues + 2 verification fixes = 7 commits
- 1 new file (`pricing/iv_smoothing.py`), 14 modified source files, 6 new test files
- 88 new tests (vs ~80 planned — 110% of target)
- 2,075 lines added, 49 removed across 25 files

### Scope Delta
- **+2 fixes** during verification: quality gate denominator, pipeline wiring gap
- **+1 file** modified beyond plan: `scoring/dimensional.py` (surface fields in FAMILY_INDICATOR_MAP)
- Otherwise scope matched plan exactly

## Effort

### Proxy Hours (from commit timestamps)
- First commit: 10:33 UTC-4
- Last commit: 11:17 UTC-4
- **Wall clock: ~44 minutes** for implementation
- **Agent compute time**: ~28 minutes across 5 parallel/sequential agents
- Planning + verification: ~15 minutes additional

### Planned Effort
- Epic size: L (Large)
- Expected: 2-4 hours for a human developer

### Ratio
- **0.7h actual / ~3h planned ≈ 0.23x** (4.3x faster than planned)

## Quality

### Test Coverage
- 88 new tests across 6 files (1,545 LOC of tests)
- 24,362 total tests passing, 0 regressions
- All lint + mypy clean

### Post-Merge Fixes
- 0 (verification fixes were pre-merge on the epic branch)

### Issues Found in Verification
1. **FR-V7 dead code**: `surface_residuals` not wired in pipeline — caught by code-analyzer agent
2. **Denominator drift**: `completeness_ratio()` field count increased → existing test shifted below threshold

## Wave Execution

| Wave | Issues | Approach | Duration |
|------|--------|----------|----------|
| 1 | #500, #502 | Parallel worktrees | ~5 min (concurrent) |
| 2 | #501 | Sequential worktree | ~4 min |
| 3 | #503 | Sequential worktree | ~9 min |
| 4 | #504 | Sequential worktree | ~10 min |
| Fix | 2 fixes | Direct on branch | ~8 min |

## Learnings

### What Went Well
1. **Parallel Wave 1** saved significant time — both agents completed independently with no conflicts
2. **Cherry-pick merge strategy** worked cleanly for worktree → epic branch integration
3. **Well-decomposed task files** with explicit "Read First" sections made agent prompts concise
4. **Config.py auto-merged** across agents (both added fields to same file, no conflict)

### What Could Improve
1. **Pipeline wiring gap** — FR-V7 tiebreaker was structurally implemented but not connected in `phase_options.py`. The task for #504 focused on `scoring/contracts.py` and `agents/_parsing.py` but the pipeline integration point was in #503's file. **Lesson**: When a feature spans the scoring→pipeline boundary, verify the full call chain end-to-end.
2. **Completeness ratio denominator drift** — Adding fields to `completeness_ratio()` shifts percentages for existing tests. **Lesson**: When adding fields to aggregate metrics, search for tests that assert specific ratios/thresholds.
3. **Worktree cleanup inconsistency** — Some worktrees auto-cleaned, others required manual cherry-pick. Standardize on one approach.

### Process Notes
- The `code-analyzer` agent caught the FR-V7 gap that all 5 implementation agents missed. **Verification is not optional.**
- Task file format with acceptance criteria + test plan made agent delegation reliable.
- The epic's wave structure (parallel Wave 1, sequential Waves 2-3) matched the dependency graph perfectly.
