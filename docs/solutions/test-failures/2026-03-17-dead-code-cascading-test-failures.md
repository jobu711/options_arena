---
title: "Dead code removal causes 20 cascading test failures from transitive dependencies"
date: 2026-03-17
module: options_arena
problem_type: test_failures
severity: high
symptoms:
  - "Tests pass before dead code removal, fail after with ImportError or AssertionError"
  - "Deleted config fields still referenced in test assertions"
  - "Hardcoded registry counts drift when functions are added/removed"
  - "Tests reference deleted prompt modules, methods, or enum members"
tags:
  - dead-code
  - test-cleanup
  - registry-count
  - cascading-failures
  - verify-loop
root_cause: "Tests have transitive dependencies on source code beyond their direct imports — config field assertions, prompt module parametrize lists, method existence checks, and hardcoded count constants all break when the source they reference is deleted."
---

## Problem

After removing ~1,720 lines of dead code across 17 modules (epic: dead-code-audit),
20 tests failed despite the source code deletions being correct. The failures were not
direct import errors but transitive dependency breakages:

- 4 tests parametrized over deleted `prompts/bull.py` and `prompts/bear.py` modules
- 4 tests asserting bull/bear argument injection into volatility dynamic prompt
- 2 tests referencing deleted `get_intelligence` API dependency provider
- 1 test asserting `OpenBBConfig.enabled` (renamed to `cboe_chains_enabled`)
- 1 test asserting deleted `enable_flow_anomaly` config field
- 2 tests calling deleted `intelligence_completeness()` method
- 4 tests expecting `neural_surface_comparison` rendering (field gating changed)
- 1 mypy error: string literals instead of `VolRegimeTier` enum values
- 1 hardcoded `MATH_FUNCTION_COUNT = 92` (actual: 88 after deletions)

## Root Cause

Three categories of transitive test dependencies:

1. **Parametrize lists**: `_PROMPT_SOURCES` in `test_prompt_structure.py` listed all prompt
   modules by string — deleting the module didn't cause an import error until the parametrized
   test tried to import it at runtime.

2. **Config field assertions**: Tests asserted `config.enabled is True` or called
   `result.intelligence_completeness()` — these methods/fields were removed from models
   but the test assertions remained.

3. **Hardcoded constants**: `MATH_FUNCTION_COUNT` in `audit.py` and `test_registry_count`
   in `test_coverage_meta.py` both hardcode function counts that drift silently when
   functions are added or removed.

## Solution

Fixed all 20 failures during the verify-loop:

- Removed deleted modules from parametrize lists
- Deleted test methods that tested removed functionality
- Updated config field assertions to use new field names
- Replaced method calls with direct attribute assertions
- Updated hardcoded constants (92→88 in audit.py, 89→88 in test_coverage_meta.py)
- Changed string literals to `VolRegimeTier` enum values

## Prevention Rule

**When deleting source code, always grep `tests/` for the deleted symbol name** — not just
`src/`. Check these specific patterns:

1. `grep -r "deleted_function_name" tests/` — direct references
2. `grep -r "deleted_module_name" tests/` — parametrize lists, string imports
3. `grep -r "deleted_config_field" tests/` — config field assertions
4. `grep -r "FUNCTION_COUNT\|registry_count" tests/` — hardcoded count constants

Allocate ~30% of dead-code-removal effort to test cleanup. The source deletions are
mechanical (grep for zero callers, delete). The test fixes require understanding each
test's intent to know whether to delete, update, or replace the assertion.

Consider making registry count assertions dynamic: `assert len(REGISTRY) == len(REGISTRY)`
is useless, but `assert len(REGISTRY) >= MINIMUM_EXPECTED` catches regressions without
breaking on intentional removals.

## Related

- Epic: `.claude/epics/archived/dead-code-audit/`
- Verification report: `.claude/epics/archived/dead-code-audit/verification-report.md`
- Retro: `.claude/epics/archived/dead-code-audit/retro.md`
- GitHub: #557-#563
