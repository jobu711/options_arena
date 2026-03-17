# Retrospective — dead-code-audit

Generated: 2026-03-16

## Summary

Removed ~1,720 lines of dead code across 17 modules, wired 8 never-connected indicator
functions into the scan pipeline, and modernized the `DebatePhase` enum to match the
6-agent protocol.

## Effort Analysis

| Metric | Planned | Actual |
|--------|---------|--------|
| Tasks | 6 | 6 |
| Hours | 14-22 | 1.1 (proxy) |
| Ratio | — | 0.06x |
| Commits | 6 | 7 (6 tasks + 1 chore) |

Proxy hours computed from first commit (19:49:02) to last commit (20:56:44) on 2026-03-16.

## Scope Delta

| Category | Planned | Delivered |
|----------|---------|-----------|
| Files changed | ~30 src + ~30 test | 40 src + 34 test = 74 |
| Lines deleted | ~1,720 | 3,634 |
| Lines added | ~200 | 359 |
| Net reduction | ~1,500 | 3,275 |
| Modules wired | 10+ indicators | 8 indicators (hurst + 7 Phase 3) |
| Groups deferred | A, B | A, B (as planned) |

Delivered more than planned: net deletion was 2x estimate due to cascading test cleanup.

## Quality Assessment

| Metric | Value |
|--------|-------|
| Post-merge fixes | 20 (19 test updates + 1 mypy fix during verification) |
| Test suite status | 15,892 passed / 27 failed (all pre-existing) |
| mypy status | 0 errors |
| ruff status | 0 errors |
| Research corrections applied | 5/5 |

### Post-Merge Fix Breakdown

All 20 fixes were test assertions referencing deleted code — the epic correctly deleted
source code but missed updating some test files that indirectly depended on removed
features:

- 4 tests referencing deleted `bull`/`bear` prompt modules
- 4 tests referencing deleted `bull`/`bear` argument injection
- 2 tests referencing deleted `get_intelligence` API dep
- 1 test referencing renamed `OpenBBConfig.enabled` field
- 1 test referencing deleted `enable_flow_anomaly` config field
- 2 tests referencing deleted `intelligence_completeness()` method
- 4 tests referencing changed `neural_surface_comparison` behavior
- 1 mypy error from string literals instead of `VolRegimeTier` enum
- 1 audit constant update (`MATH_FUNCTION_COUNT` 92→88)

## Learnings

1. **Test cleanup is the long tail of dead code removal**. The source code deletions were
   straightforward (grep for zero callers, delete). But tests had transitive dependencies
   — tests importing deleted prompts, testing deleted config fields, asserting removed
   methods. A future dead-code epic should allocate 30% of effort to test cleanup.

2. **Research phase prevents catastrophic mistakes**. The research doc identified 5 critical
   corrections (e.g., `spread_analysis` is LIVE, not dead). Without research, Wave 1 would
   have broken production behavior.

3. **Registry constants drift silently**. `MATH_FUNCTION_COUNT` and `test_registry_count`
   both hardcode counts that drift when functions are added/removed. Consider making these
   dynamic (`len(MATH_FUNCTION_REGISTRY)`) rather than hardcoded.

4. **Wave structure works well for large refactors**. Sequential waves (delete → cleanup →
   wire) prevented merge conflicts and made each commit independently verifiable.

## Wave-by-Wave Summary

| Wave | Task | Commit | Impact |
|------|------|--------|--------|
| 1 | #558 Legacy debate removal | b8adcae | ~1,100 lines deleted across 17 modules |
| 2 | #559 Dead function removal | 9899647 | ~620 lines deleted across 16 modules |
| 3 | #560 Re-export cleanup | 6104385 | Clean exports, deduplicate sentinel |
| 4a | #561 Wire hurst_exponent | 6f4f3bd | Phase 2 pipeline integration |
| 4b | #562 Wire Phase 3 indicators | edb3f72 | 7 indicators + skew helper |
| 4c | #563 Modernize DebatePhase | d7fd5b2 | 6-agent enum + progress callback |
