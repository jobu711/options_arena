---
title: Test Tier Optimization
status: approved
created: 2026-03-11
---

# PRD: Test Tier Optimization

## Problem

The test suite has grown to ~4,400 tests (24K parametrized) across 263 files. Claude Code
agents get blocked during epic development waiting for the full suite to complete. CI runs
everything — including 12K+ pricing stress grid parametrizations — on every push. The
existing `smoke` marker (10 tests) is underutilized, and there's no tiered execution strategy.

## Goals

1. Agent verification in <30s via a `critical` marker tier (50-80 tests)
2. CI stops wasting time on exhaustive tests per-push (nightly schedule for stress grids)
3. Fresh marker taxonomy replaces the ad-hoc smoke/slow system

## Requirements

### Functional Requirements

- FR-01: Replace `smoke` marker with `critical` (critical-path tests for <30s agent/pre-commit)
- FR-02: Replace `slow` marker with `exhaustive` (stress grids and large parametrize matrices)
- FR-03: Keep `db` and `integration` markers (useful for filtering, low cost)
- FR-04: Expand `critical` tier to 50-80 tests covering all modules' happy paths
- FR-05: CI push/PR job excludes `exhaustive` tests (`-m "not exhaustive"`)
- FR-06: CI nightly job runs full suite including `exhaustive`
- FR-07: `conftest.py` emits informational warning for tests with no tier marker
- FR-08: Update CLAUDE.md, tests/CLAUDE.md, agent configs with new marker names

### Non-Functional Requirements

- NFR-01: `critical` tier completes in <30s
- NFR-02: No source code changes — only test infrastructure and documentation
- NFR-03: All existing tests continue to pass

## Success Criteria

- [ ] `uv run pytest -m critical -q` runs <30s and covers all modules
- [ ] `uv run pytest -m "not exhaustive" -n auto -q` passes (standard CI suite)
- [ ] `uv run pytest -n auto -q` passes (full suite including exhaustive)
- [ ] CI workflow has separate push and nightly jobs
- [ ] Marker taxonomy documented in pyproject.toml, tests/CLAUDE.md, and CLAUDE.md
