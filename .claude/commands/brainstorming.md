---
allowed-tools: Read, Glob, Grep, Bash, Agent, AskUserQuestion, Write, Edit
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming

Structured design thinking that produces a PRD — the thorough entry point into the
`/pm:prd-research` -> `/pm:prd-parse` pipeline.

## Usage
```
/brainstorming <feature_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Hard Gate

**You MUST NOT write any implementation code during this skill.** No source files, no tests,
no config changes. The only file you create is the PRD at the end. If the user asks you to
start coding, remind them: "Let's finish the design first — implementation comes after
`/pm:prd-research` or `/pm:prd-parse`."

## Preflight Checklist

Complete silently — do not narrate these checks to the user.

### Input Validation
1. **Validate feature name format:**
   - Must contain only lowercase letters, numbers, and hyphens
   - Must start with a letter
   - If invalid: "Feature name must be kebab-case (lowercase letters, numbers, hyphens). Examples: user-auth, payment-v2, notification-system"

2. **Check for existing PRD:**
   - Check if `.claude/prds/$ARGUMENTS.md` already exists
   - If it exists, ask user: "PRD '$ARGUMENTS' already exists. Overwrite it?"
   - Only proceed with explicit confirmation
   - If no: "Use a different name or run: /pm:prd-parse $ARGUMENTS to create an epic from the existing PRD"

3. **Verify directory structure:**
   - Check if `.claude/prds/` directory exists
   - If not, create it

## Steps

### Step 1 — Explore Project Context

Before asking the user anything, silently gather context:

- Read `CLAUDE.md`, `.claude/context/progress.md`, `.claude/context/system-patterns.md`
- Glob for files related to the feature name (`$ARGUMENTS`)
- Check recent git commits (`git log --oneline -20`)
- Scan existing PRDs in `.claude/prds/` for related work
- Look at open GitHub issues if relevant (`gh issue list` if available)

Summarize what you found in 3-5 bullet points. Example:
> Based on the codebase, here's what I see:
> - The project already has X which relates to this feature
> - There's existing infrastructure in `module/` that could be leveraged
> - No prior PRD or epic covers this area

### Step 2 — Clarifying Questions (One at a Time)

Ask **one question at a time** using `AskUserQuestion` with multiple-choice options.
Do NOT dump a list of questions. Wait for each answer before asking the next.

Cover these areas (skip any already answered by the user's initial request):

1. **Core problem**: "What specific problem does this solve for users?"
2. **Scope**: "How large should the first version be?" (Options: Minimal MVP / Moderate / Full-featured)
3. **Users**: "Who is the primary user?" (Options derived from project context)
4. **Constraints**: "Any hard constraints?" (timeline, tech stack, compatibility)
5. **Success criteria**: "How will we know this works?" (Options: specific metrics, user feedback, etc.)

Stop asking when you have enough to propose approaches (usually 3-5 questions).
If the user says "that's enough" or similar, move on immediately.

### Step 3 — Propose 2-3 Approaches

Present 2-3 distinct implementation approaches. For each:

```
### Approach A: [Name]
**How it works**: [2-3 sentences]
**Pros**: [Bullet list]
**Cons**: [Bullet list]
**Complexity**: Low / Medium / High
**Fits existing architecture**: Yes / Partially / No
```

End with a clear recommendation:
> **Recommended: Approach B** — [one sentence why]

Ask the user to pick one (or suggest a hybrid) using `AskUserQuestion`.

### Step 4 — Present Design Incrementally

Present the design in sections, getting approval on each before moving to the next.
Use `AskUserQuestion` after each section with options: "Looks good" / "Needs changes".

**Section order:**

1. **Architecture & Module Changes**
   - Which modules are affected
   - New files/models needed
   - How it fits the boundary table in CLAUDE.md

2. **Data Models & Types**
   - New Pydantic models, enums, config fields
   - Field types following project conventions (Decimal for prices, float for ratios, etc.)

3. **Core Logic & Flow**
   - Algorithm or business logic overview
   - Integration points with existing pipeline

4. **API / CLI Surface** (if applicable)
   - New commands, endpoints, or UI components

5. **Testing Strategy**
   - What tests are needed
   - Edge cases to cover

If the user requests changes to a section, revise and re-present that section only.

### Step 5 — Write the PRD

Once all sections are approved, write the PRD to `.claude/prds/$ARGUMENTS.md`.

**Get the real current datetime** by running: `date -u +"%Y-%m-%dT%H:%M:%SZ"`

**File format:**

```markdown
---
name: $ARGUMENTS
description: [Brief one-line description]
status: backlog
created: [Real ISO datetime from system]
---

# PRD: $ARGUMENTS

## Executive Summary
[Value proposition — what and why, derived from Step 2 answers]

## Problem Statement
### What problem are we solving?
[From Step 2 core problem discussion]

### Why is this important now?
[Context from Step 1 exploration — existing infrastructure, user demand, etc.]

## User Stories
[From Step 2 users discussion, with acceptance criteria]

## Architecture & Design
### Chosen Approach
[The selected approach from Step 3, with rationale]

### Module Changes
[From Step 4 Section 1]

### Data Models
[From Step 4 Section 2]

### Core Logic
[From Step 4 Section 3]

## Requirements
### Functional Requirements
[Derived from Steps 2-4]

### Non-Functional Requirements
[Performance, security, compatibility — from Step 2 constraints]

## API / CLI Surface
[From Step 4 Section 4, or "N/A" if none]

## Testing Strategy
[From Step 4 Section 5]

## Success Criteria
[Measurable outcomes from Step 2]

## Constraints & Assumptions
[From Step 2 constraints discussion]

## Out of Scope
[Explicitly listed — things discussed but deferred]

## Dependencies
[External and internal dependencies identified during design]
```

### Step 6 — Transition

After writing the PRD:

1. Confirm: "PRD created: `.claude/prds/$ARGUMENTS.md`"
2. Show a 3-line summary of what was captured
3. Suggest next steps:
   > Ready to research the codebase? Run: `/pm:prd-research $ARGUMENTS`
   > (Or skip research and go directly to: `/pm:prd-parse $ARGUMENTS`)

## Error Recovery

- If any step fails, explain what went wrong and how to fix it
- Never leave partial or corrupted files
- If the user abandons mid-session, do not write the PRD

## Tips

- Prefer concrete examples over abstract descriptions
- Reference existing code and patterns from the codebase when proposing approaches
- Keep the PRD focused — if scope creeps, suggest splitting into multiple PRDs
- The PRD should be detailed enough that `/pm:prd-parse` can decompose it into an epic without ambiguity
