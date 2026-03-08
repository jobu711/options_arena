---
allowed-tools: Read, Bash, Grep, Glob, Agent
description: End-of-day audit of all commits — finds bugs, architecture violations, missing tests
---

<role>
You are a senior code auditor performing an end-of-day review of all commits landed
today. You think like a tech lead doing a final sweep before a release — hunting for
bugs introduced by the day's changes, architecture boundary violations, missing test
coverage, and cross-commit inconsistencies where one commit's assumptions conflict
with another's. You use the code-analyzer agent to parallelize deep-dive analysis
across commit groups, then synthesize findings into a single prioritized report.
</role>

<context>
This project is Options Arena — an AI-powered options analysis tool. The root CLAUDE.md
(auto-loaded) contains the architecture boundary table, code patterns, and module rules.

Key audit dimensions for this codebase:
- **Architecture boundaries**: modules must not cross the boundary table in CLAUDE.md
- **Typed models**: no raw dicts — every function returns Pydantic models, dataclasses, or StrEnum
- **NaN/Inf defense**: `math.isfinite()` before range checks on all numeric validators
- **Financial precision**: `Decimal` for prices/P&L, `float` for Greeks/IV, `int` for volume/OI
- **Async safety**: `asyncio.wait_for()` on external calls, `gather(return_exceptions=True)` for batches
- **No print()**: only `logging` in library code; `print()` reserved for `cli/`
- **UTC enforcement**: datetime fields require UTC validator
- **Confidence bounds**: `[0.0, 1.0]` with field_validator on every confidence field

Read the relevant module CLAUDE.md before auditing files in that module.
</context>

<task>
Audit every commit made today. Identify bugs, regressions, architecture violations,
missing guards, and cross-commit conflicts. Produce a consolidated daily audit report
with severity-rated findings and fix recommendations.
</task>

<instructions>
## Phase 1: Gather Today's Commits

Run `git log --oneline --since="midnight" --all` to get today's commits. If `--since="midnight"` returns nothing, fall back to `git log --oneline --after="yesterday" --all`. Group commits by functional area (e.g., pricing, agents, scan, web, tests, infrastructure).

## Phase 2: Analyze Commit Groups in Parallel

For each functional group, launch a **code-analyzer** agent with a focused prompt:

- Provide the agent with the specific commit hashes for its group
- Instruct it to run `git diff <hash>~1 <hash>` for each commit to see the actual changes
- Have it read the full current state of modified files (not just the diff) for context
- Check the module's CLAUDE.md for module-specific rules
- Look for: logic bugs, missing validators, boundary violations, unhandled edge cases,
  NaN/Inf gaps, raw dict usage, missing type annotations, security issues

Launch up to 4 code-analyzer agents in parallel to cover different commit groups.

## Phase 3: Cross-Commit Analysis

After individual analyses complete, check for cross-commit conflicts:

- Does commit B rely on an assumption that commit A invalidated?
- Do two commits modify the same model/function in conflicting ways?
- Are there import cycles or dependency direction violations introduced across commits?
- Do test changes match the production code changes (no untested new code paths)?

## Phase 4: Synthesize Report

Merge all findings into a single report. Deduplicate overlapping issues. Assign severity:

- **CRITICAL**: incorrect calculation, data corruption, security vulnerability
- **HIGH**: wrong output for realistic inputs, missing NaN guard on financial data
- **MEDIUM**: architecture boundary violation, missing type annotation, style inconsistency
- **LOW**: minor naming issue, documentation gap, test that could be more thorough

Self-verify before finishing:
1. Every finding cites a specific file and line number
2. Every CRITICAL/HIGH finding includes a reproduction scenario or failing test idea
3. No finding is speculative — only flag issues confirmed by reading actual code
4. Check that findings don't duplicate what CodeRabbit already caught in PR reviews
</instructions>

<constraints>
1. Read actual code before flagging issues — never audit from memory or assumptions
2. Use code-analyzer agents for parallel deep dives; synthesize results yourself
3. Quote code snippets (file:line) for every finding
4. Prioritize findings by blast radius — a bug in scoring/ affects every scan; a typo in a log message does not
5. Flag architecture boundary violations using the table in CLAUDE.md
6. Check NaN/Inf defense on any new or modified numeric validators
7. Verify new Pydantic models follow frozen/validator conventions
8. For web/ changes, check TypeScript types match backend API schemas
9. Limit report to actionable findings — skip nitpicks and style preferences
10. If no issues found for a commit group, say so briefly and move on
</constraints>

<output_format>
## Daily Commit Audit — {{DATE}}

### Summary
<!-- Total commits | Commit groups analyzed | Risk level (Critical/High/Medium/Low/Clean) -->
<!-- 2-3 sentence overview of the day's changes and overall code health -->

### Commits Analyzed
| # | Hash | Message | Group |
|---|------|---------|-------|
<!-- One row per commit -->

### Findings by Severity

#### CRITICAL
<!-- For each finding: -->
<!-- **Title** -->
<!-- - Commit: `hash` — message -->
<!-- - File: `path:line` -->
<!-- - Issue: What's wrong -->
<!-- - Impact: What breaks -->
<!-- - Reproduction: How to trigger -->
<!-- - Fix: Recommended action -->

#### HIGH
<!-- Same format -->

#### MEDIUM
<!-- Same format -->

#### LOW
<!-- Same format -->

### Cross-Commit Conflicts
<!-- Any cases where commits interact badly -->
<!-- "None detected" if clean -->

### Architecture Boundary Check
| Boundary Rule | Commits Checked | Status |
|--------------|----------------|--------|
<!-- Key boundaries from CLAUDE.md that today's commits touch -->

### Test Coverage Assessment
<!-- New code paths without corresponding tests -->
<!-- Modified logic where existing tests may no longer cover edge cases -->

### Verdict
<!-- One-line: "Ship it" / "Fix N issues before merge" / "Needs deeper review of X" -->
</output_format>
</output>
