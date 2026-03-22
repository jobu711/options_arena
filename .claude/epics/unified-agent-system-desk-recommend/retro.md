# Retrospective — unified-agent-system-desk-recommend

**Date:** 2026-03-22
**Duration:** ~1 session (decompose + sync + execute)
**Branch:** epic/unified-agent-system-desk-recommend

## Effort Summary

| Metric | Planned | Actual | Ratio |
|--------|---------|--------|-------|
| Tasks | 6 | 6 | 1.0x |
| Source LOC | 600-900 | 1,089 | 1.3x |
| Test LOC | 200-300 | 1,117 | 4.3x |
| Test cases | ~56 | 94 new (159 total) | 1.7x |
| Test files | 9 | 9 (14 new files total) | 1.0x |
| Proxy hours | 16-22h | ~2h (agent-assisted) | 0.1x |

## What Went Well

1. **Parallel agent execution worked perfectly.** Wave 1 (3 foundation tasks) and Wave 2 (3 desk tasks) ran with zero merge conflicts despite touching adjacent code.

2. **Pattern consistency.** All 6 desk recommendation agents follow identical architecture: dual-instance `Agent`, `@system_prompt(dynamic=True)`, `@output_validator`, never-raises runner, fallback builder. This made the task highly parallelizable.

3. **Foundation epic paid off.** `DomainAssessment` hierarchy, `AnyAssessment` discriminated union, and `PositionRecommendation` from the foundation epic were ready and correct — zero changes needed.

4. **Zero regressions.** 138 existing interactive desk tests pass unchanged. DeskDeps extension was fully backward-compatible with optional fields at the end.

5. **Test coverage exceeded plan.** 94 new tests vs ~56 planned (167%). Agents added extra tests for model_settings acceptance, correct ticker in fallback, etc.

## What Could Improve

1. **Test LOC significantly exceeded estimate.** 1,117 test LOC vs 200-300 planned. The prompt tests alone generated 86 tests with parametrization. Estimate was too conservative for structured parametrized tests.

2. **Sub-agent file writes failed silently.** During decomposition, agents reported task files created but they didn't actually exist — had to recreate manually. Need to verify agent outputs for file-creation tasks.

3. **`gh sub-issue` API surface.** Spent time debugging `--body-file` (not supported) and `--parent`/`--child` (positional args, not flags). Document correct syntax.

## Scope Delta

| Scope | Planned | Delivered | Delta |
|-------|---------|-----------|-------|
| DeskDeps fields | 3 new optional | 3 new optional | Exact |
| Cleaner function | 1 generic function | 1 generic function (PEP 695) | Exact |
| Prompts | 6 files | 6 files | Exact |
| Recommendation agents | 6 dual-instance | 6 dual-instance | Exact |
| Runner functions | 6 never-raises | 6 never-raises | Exact |
| Re-exports | `__init__.py` updates | `__init__.py` + `prompts/__init__.py` | +1 file |

**No scope creep. No deferred items.**

## Learnings

1. **Dual-instance PydanticAI pattern works well.** Two `Agent` instances sharing a toolset but with different `output_type` (str vs Pydantic model) is clean and maintainable. Good pattern to reuse.

2. **`model_copy(update=...)` is the right approach for frozen model cleaning.** Generic field iteration + model_copy avoids per-subclass logic. Works for any DomainAssessment subclass.

3. **Recommendation prompts should use `PROMPT_RULES_APPENDIX`.** Unlike conversational desk prompts, recommendation prompts need the confidence calibration scale for structured output quality.

## Quality Assessment

- **Post-merge fixes needed:** 0
- **Lint issues found:** 0
- **Type errors found:** 0
- **Test failures:** 0 / 297
- **Regression count:** 0
