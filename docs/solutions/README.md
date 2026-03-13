# Solutions Knowledge Base

Structured knowledge capture for Options Arena. Every solved problem becomes a
searchable entry preventing future repetition.

## Purpose

- **Capture**: Record root causes, solutions, and prevention rules after solving problems
- **Retrieve**: Grep-first search before starting work in known-fragile areas
- **Compound**: Knowledge accumulates — first fix is research, subsequent fixes are lookup

## How to Add Entries

Use the `/compound` command after solving a problem. It auto-generates frontmatter and
places the file in the correct category directory.

Manual creation: `docs/solutions/{category}/YYYY-MM-DD-{slug}.md`

## Entry Schema (YAML Frontmatter)

```yaml
---
title: "Descriptive title of the problem and solution"
date: YYYY-MM-DD
module: options_arena.{module}
problem_type: pricing_error|boundary_violation|nan_defense|async_bug|
              yfinance_gotcha|pydantic_pattern|test_failure|
              performance_issue|config_error|integration_issue
severity: critical|high|medium|low
symptoms:
  - "Observable symptom 1"
  - "Observable symptom 2"
tags:
  - keyword1
  - keyword2
root_cause: Brief one-line description of the root cause
---

## Problem

What was observed? What broke? Include error messages if applicable.

## Root Cause

Technical explanation of why it happened. Reference specific code paths.

## Solution

What was changed and why. Include code snippets if helpful.

## Prevention Rule

Concrete, actionable rule that prevents recurrence. This is the most important section.

## Related

- Links to other solution entries, GitHub issues, or documentation
```

## Categories

| Directory | Problem Type | Examples |
|-----------|-------------|----------|
| `pricing-errors/` | BSM/BAW bugs, Greek computation issues | Wrong vega formula, missing dividend yield |
| `boundary-violations/` | Module import violations, architecture drift | scoring/ importing pricing/bsm directly |
| `nan-defense/` | NaN/Inf corruption, isfinite() misses | NaN passing range validators |
| `async-bugs/` | Race conditions, timeout issues, gather failures | to_thread pre-call, missing return_exceptions |
| `yfinance-gotchas/` | Data source quirks, API changes | Missing Greeks, stale quotes |
| `pydantic-patterns/` | Model validation, serialization, v2 patterns | Frozen model issues, validator ordering |
| `test-failures/` | Test isolation, fixture patterns, flaky tests | Missing mocks, date-dependent tests |
| `performance-issues/` | Slow queries, N+1, pipeline bottlenecks | Unbatched API calls, missing cache |
| `config-errors/` | Settings, env vars, nested config | Wrong env prefix, missing defaults |
| `integration-issues/` | Service interactions, fallback chains | CBOE timeout, OpenBB import failure |

## How to Search

The `learnings-researcher` agent automates retrieval. Manual search:

```bash
# By module
grep -rl "module:.*pricing" docs/solutions/

# By tag
grep -rl "tags:.*nan\|isfinite" docs/solutions/

# By symptom
grep -rl "symptoms:.*NaN" docs/solutions/

# Full-text
grep -rl "brentq" docs/solutions/
```
