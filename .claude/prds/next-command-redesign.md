---
name: next-command-redesign
description: Fix AskUserQuestion rendering bug, improve backlog mining accuracy, add strategic vision, reduce context burn
status: planned
created: 2026-03-08T22:00:00Z
---

# PRD: next-command-redesign

## Executive Summary

The `/pm:next` command has a critical rendering bug where AskUserQuestion never fires,
plus accuracy issues (suggests shipped features) and excessive context consumption. This
redesign fixes the tool invocation pattern, adds cross-referencing to eliminate false
positives, introduces strategic vision suggestions beyond the existing backlog, and cuts
context usage by ~50%.

## Problem Statement

### P1: AskUserQuestion Never Renders (Critical Bug)

The Phase 1 interview uses a JSON code fence to specify the AskUserQuestion call:

```
Ask all 3 questions in ONE AskUserQuestion call. Use this exact structure:

\`\`\`json
{ "questions": [ ... ] }
\`\`\`
```

Claude treats this as example documentation, not a tool invocation directive. Three
compounding issues:

1. **JSON-in-code-fence**: Claude sees fenced JSON as a documentation example, not an
   instruction to call a tool. The model reads it as "here is what the schema looks like"
   rather than "call this tool with these parameters."

2. **Text-before-tool ordering**: The instruction says "Output this exact text... then
   immediately call AskUserQuestion." This puts Claude into text-generation mode first.
   Once generating text, the model tends to continue generating text rather than switching
   to tool mode.

3. **Negative constraint suppression**: "Do NOT run any bash commands... before OR
   alongside this call" and "Do NOT include any other tool calls alongside" — negative
   framing can suppress the target tool call itself, not just the prohibited ones.

**Result**: Claude skips the interview entirely and jumps to Phase 2 context gathering.

### P2: Backlog Mining False Positives

The command suggests features that have already shipped. Current cross-referencing checks
PRDs against merge log and archived epics, but:

- Does not check `progress.md` "Recently Completed" section
- Does not verify against actual codebase (e.g., suggesting "add heatmap" when
  `web/src/views/MarketHeatmap.vue` already exists)
- PRD `status` field in frontmatter is not consulted

### P3: No Strategic Vision

When the backlog is exhausted, the command has a single fallback line: "suggest genuinely
new directions based on what the codebase enables." This produces vague suggestions. There
is no structured approach to analyzing capabilities, identifying gaps, or referencing
industry patterns.

### P4: Context Window Burn

Phase 2 runs four parallel git commands plus per-branch inspection, reads PRD content, and
processes merge history. On a project with 384+ closed issues and 26 archived epics, this
consumes ~20-30% of context window before any ranking begins.

## User Stories

### US-1: Interactive Interview

**As a** developer running `/pm:next`,
**I want to** see an interactive 3-question form before any recommendations,
**so that** I can steer the output to match my current headspace.

**Acceptance Criteria:**
- AskUserQuestion renders as an interactive form on every invocation
- The form blocks execution until the user responds
- Three questions appear: Mode, Area, Scope (same content as current)
- No context gathering occurs before the user answers

### US-2: Accurate Recommendations

**As a** developer reviewing recommendations,
**I want to** see only genuinely actionable items (not shipped features),
**so that** I don't waste time investigating work that's already done.

**Acceptance Criteria:**
- Zero false positives: never recommends features visible in `progress.md` "Recently
  Completed" or present in the codebase
- Each recommendation is verified against at least two sources (PRD status + code presence)
- Output includes a "Filtered out (already shipped)" section showing what was excluded

### US-3: Strategic Suggestions

**As a** developer on a mature project with few backlog items,
**I want to** see genuinely novel strategic directions alongside backlog items,
**so that** I can discover high-impact work I haven't thought of yet.

**Acceptance Criteria:**
- Output separates "Backlog Items" from "Strategic Opportunities"
- At least 1 strategic suggestion per run (even when backlog items exist)
- Strategic suggestions reference what the architecture enables, not just what's missing
- Suggestions are grounded in specific codebase capabilities (e.g., "the pricing engine
  supports X, enabling Y")

### US-4: Fast and Lean Execution

**As a** developer with a limited context window,
**I want to** the command to gather context efficiently,
**so that** I have plenty of context remaining for the actual implementation work.

**Acceptance Criteria:**
- Context gathering uses <15% of context window (down from ~25-30%)
- Command completes in under 60 seconds
- PRDs are read as frontmatter only (first 10 lines), not full content
- Heavy analysis is delegated to a subagent to protect main context

## Functional Requirements

### FR-1: Fix Interview Rendering

Replace the JSON code fence with prose-based AskUserQuestion directives.

**Current (broken):**
```
1. Output this exact text: "Let me ask..."
2. Immediately call AskUserQuestion with the 3 questions below.
3. Do NOT run any bash commands... before OR alongside this call.

Ask all 3 questions in ONE AskUserQuestion call. Use this exact structure:
\`\`\`json
{ "questions": [...] }
\`\`\`
```

**New pattern:**
- Lead with a direct positive instruction: "Your first action is to call AskUserQuestion"
- Describe questions as bulleted prose with field names inline
- No JSON blocks, no code fences for tool parameters
- No preceding text output — the tool call IS the first action
- Remove negative constraints entirely; rely on ordering ("Phase 2 begins AFTER answers")

### FR-2: Smarter Backlog Mining

Multi-source cross-referencing to eliminate false positives:

1. **PRD frontmatter check**: Read `status` field from each `.claude/prds/*.md` — skip any
   with `status: done` or `status: archived`
2. **Progress.md check**: Read "Recently Completed" section — skip any feature mentioned
3. **Archived epics check**: Glob `.claude/epics/archived/` — skip any matching epic name
4. **Code existence check**: For each candidate, glob/grep for evidence it's already
   implemented (e.g., check for Vue components, API endpoints, model classes)
5. **Branch check**: Only flag truly unmerged branches (`git branch --no-merged master`)

### FR-3: Strategic Vision Suggestions

Structured approach to generating novel suggestions:

1. **Capability analysis**: Identify what the current architecture enables but doesn't yet
   do (e.g., "real-time WebSocket infrastructure exists but only serves scans — could
   power live price feeds")
2. **Gap analysis**: Compare module maturity — which modules have the most room to grow?
3. **Industry patterns**: Reference standard features in comparable tools (options
   analytics platforms, trading dashboards) that Options Arena lacks
4. **Output format**: Separate section "Strategic Opportunities" with different formatting
   from backlog items — clearly marked as new ideas vs existing plans

### FR-4: Leaner Execution

Reduce context consumption:

1. **Delegate context sweep**: Use Agent tool (Explore subagent) for git history and PRD
   scanning — results stay in subagent context, only summary returns
2. **Targeted git queries**: Replace 4 parallel git commands with:
   - `git log master --oneline -10` (recent commits only)
   - `git branch --no-merged master` (unmerged branches only)
3. **PRD frontmatter only**: Read first 10 lines of each PRD (captures YAML frontmatter),
   not full content
4. **Skip per-branch inspection**: Don't enumerate commits per unmerged branch — just
   note the branch exists and its name implies the feature

## Non-Functional Requirements

### NFR-1: Performance
- Command completes in under 60 seconds end-to-end
- Interview phase renders within 2 seconds of command invocation

### NFR-2: Context Efficiency
- Total context consumed by Phase 2 must not exceed ~15% of window
- Use subagent delegation for heavy analysis

### NFR-3: Output Scannability
- Final output scannable in under 30 seconds
- Each recommendation is 3-5 lines maximum
- Clear visual separation between backlog items and strategic suggestions

### NFR-4: Reliability
- Command must work on fresh clones (no dependency on local state beyond git)
- Graceful degradation if `.claude/prds/` or `.claude/epics/` directories are empty

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| AskUserQuestion renders | Never (bug) | 100% of invocations |
| False positives (shipped features suggested) | Common | Zero |
| Strategic suggestions per run | 0 | >= 1 |
| Context window usage (Phase 2) | ~25-30% | < 15% |
| Time to completion | Variable | < 60 seconds |

## Out of Scope

- Changing the number of interview questions (stays at 3: Mode, Area, Scope)
- Auto-creating epics or PRDs from recommendations
- Integration with external project management tools (Jira, Linear, etc.)
- Modifying other `/pm:*` commands
- Changing the ranking multiplier tables (weight tuning is a separate concern)

## Technical Notes

### AskUserQuestion Rendering Pattern

The working pattern for tool invocation in `.claude/commands/` markdown:

**Do**: Use prose directives with positive framing
```
Your first action is to call AskUserQuestion with these 3 questions:

- Question 1 (header: "Mode", single-select): "What kind of work...?"
  Options: "Build new features" / "Fix and harden" / "Polish and refine" / "Surprise me"

- Question 2 (header: "Area", multi-select): "Which parts of the codebase...?"
  Options: "Backend (Python)" / "Frontend (Vue)" / "AI agents" / "Infrastructure"

- Question 3 (header: "Scope", single-select): "How much time...?"
  Options: "Quick wins (hours)" / "Focused sprint (days)" / "Deep project (week+)"

Phase 2 begins AFTER the user answers.
```

**Don't**: Use JSON code fences, text-before-tool ordering, or negative constraints.

### Verification Plan

1. **Manual test**: Run `/pm:next` and verify AskUserQuestion renders as interactive form
2. **False positive check**: Verify recommendations don't include any feature listed in
   `progress.md` "Recently Completed"
3. **Strategic suggestion check**: Confirm at least 1 suggestion is genuinely novel (not
   in any PRD or backlog)
4. **Context measurement**: Compare context usage before and after by checking remaining
   context after Phase 2 completes
