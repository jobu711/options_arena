---
name: Autonomous Task
about: Structured task for Claude Code execution
labels: auto-task
---

## Metadata
- **Module Scope**: <!-- comma-separated: models, pricing, indicators, services, scoring, data, scan, agents, cli, api, reporting, web -->
- **Zone**: <!-- foundation | engine | interface -->
- **Complexity**: <!-- S | M | L -->
- **Blocked By**: <!-- #NNN, #NNN or none -->
- **Blocks**: <!-- #NNN, #NNN or none -->

## Files to Modify
```
src/options_arena/module/file.py
tests/unit/module/test_file.py
```

## Files to Create
```
```

## Description

<!-- Detailed implementation instructions.
     Be specific: function signatures, model fields, algorithm steps.
     Reference existing code patterns the instance should follow. -->

## Acceptance Criteria

- [ ] <!-- task-specific criterion -->
- [ ] All existing tests pass (1,577 Python + 38 E2E if web/api touched)
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy src/ --strict` clean

## Test Requirements

<!-- Specific test functions to add/modify, one per line -->
- Add `test_function_name()` in `tests/unit/module/test_file.py`

## Context Files to Read
<!-- CLAUDE.md files to read before starting -->
- `CLAUDE.md`
- `src/options_arena/{module}/CLAUDE.md`
