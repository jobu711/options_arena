---
allowed-tools: Read, Glob, Grep, Write, Bash
description: "Capture a solved problem to docs/solutions/ for future retrieval"
---

# Compound — Knowledge Capture

Capture a solved problem from the current conversation into `docs/solutions/` with
structured YAML frontmatter for grep-based retrieval.

## Usage

```
/compound {short description of what was learned}
```

## Instructions

### 1. Parse the Learning

From `$ARGUMENTS` and the conversation context, determine:
- **What went wrong** (the problem)
- **Why it went wrong** (root cause)
- **How it was fixed** (solution)
- **How to prevent it** (prevention rule)

### 2. Classify the Problem

Determine the category from the module and problem type:

| Category | When to use |
|----------|------------|
| `pricing-errors` | BSM/BAW bugs, Greek computation issues |
| `boundary-violations` | Module import violations, architecture drift |
| `nan-defense` | NaN/Inf corruption, isfinite() misses |
| `async-bugs` | Race conditions, timeout issues, gather failures |
| `yfinance-gotchas` | Data source quirks, API changes |
| `pydantic-patterns` | Model validation, serialization, v2 patterns |
| `test-failures` | Test isolation, fixture patterns, flaky tests |
| `performance-issues` | Slow queries, N+1, pipeline bottlenecks |
| `config-errors` | Settings, env vars, nested config |
| `integration-issues` | Service interactions, fallback chains |

### 3. Check for Duplicates

```bash
grep -rl "{key_term}" docs/solutions/
```

If a similar entry exists, offer to **update** the existing entry instead of creating a
new one. Read the existing entry and ask if they should be merged.

### 4. Generate the Entry

Filename: `YYYY-MM-DD-{slug}.md` where slug is 3-5 lowercase hyphenated words.

Use today's date. Generate the file with the schema from `docs/solutions/README.md`:

```yaml
---
title: "{descriptive title}"
date: {today}
module: options_arena.{module}
problem_type: {category_without_hyphens}
severity: critical|high|medium|low
symptoms:
  - "{observable symptom}"
tags:
  - {keyword1}
  - {keyword2}
root_cause: "{one-line root cause}"
---

## Problem
{What was observed}

## Root Cause
{Technical explanation}

## Solution
{What was changed}

## Prevention Rule
{Actionable rule}

## Related
- {Links to issues, other entries, or docs}
```

### 5. Write and Confirm

Write the file to `docs/solutions/{category}/{filename}.md`.

Output:
```
Captured: {title}
  File: docs/solutions/{category}/{filename}.md
  Category: {category}
  Tags: {tag1}, {tag2}
```
