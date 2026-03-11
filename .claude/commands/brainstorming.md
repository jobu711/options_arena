---
allowed-tools: Read, Glob, Grep, Bash, Write, Edit
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

## Critical: Conversation Turn Discipline

This command uses **natural conversation turns** for user interaction. You output text, then
**STOP and wait for the user to respond**. You do NOT use `AskUserQuestion`. You do NOT
continue past a stop point under any circumstances.

There are **3 mandatory stop points** in this flow. At each one you MUST:
1. End your message with the stop marker (shown below)
2. **Actually stop generating** — do not continue to the next phase
3. Wait for the user's next message before proceeding

## Phases

### Phase 1 — Discover

#### Preflight (silent — do not narrate)

1. **Validate feature name format:**
   - Must contain only lowercase letters, numbers, and hyphens
   - Must start with a letter
   - If invalid: "Feature name must be kebab-case (lowercase letters, numbers, hyphens). Examples: user-auth, payment-v2, notification-system"

2. **Check for existing PRD:**
   - Check if `.claude/prds/$ARGUMENTS.md` already exists
   - If it exists, tell the user: "PRD '$ARGUMENTS' already exists. Let me know if you want to overwrite it, or use a different name. You can also run `/pm:prd-parse $ARGUMENTS` to create an epic from the existing PRD."
   - **STOP and wait for the user's response before continuing.**

3. **Verify directory structure:**
   - Check if `.claude/prds/` directory exists
   - If not, create it

#### Context Exploration (silent — do not narrate individual steps)

- Read `CLAUDE.md`, `.claude/context/progress.md`, `.claude/context/system-patterns.md`
- Glob for files related to the feature name (`$ARGUMENTS`)
- Check recent git commits (`git log --oneline -20`)
- Scan existing PRDs in `.claude/prds/` for related work
- Look at open GitHub issues if relevant (`gh issue list` if available)

#### Present Findings + Ask Questions

Summarize what you found in 3-5 bullet points. Example:
> Based on the codebase, here's what I see:
> - The project already has X which relates to this feature
> - There's existing infrastructure in `module/` that could be leveraged
> - No prior PRD or epic covers this area

Then present **all clarifying questions at once** as a numbered list. Cover these areas
(skip any already answered by the user's initial request):

1. **Core problem**: What specific problem does this solve?
2. **Scope**: How large should the first version be? (Minimal MVP / Moderate / Full-featured)
3. **Users**: Who is the primary user of this feature?
4. **Constraints**: Any hard constraints? (timeline, tech stack, compatibility)
5. **Success criteria**: How will we know this works?

End with:
---
**Your turn** — answer the questions above (as much or as little as you like).

**STOP. End your turn. Do not continue until the user responds.**
Do not propose approaches. Do not start designing. Do not write the PRD. Wait for the user.

---

### Phase 2 — Propose

Read the user's answers from their previous message. Then present 2-3 distinct approaches:

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

End with:
---
**Your turn** — pick an approach (A, B, C) or suggest a hybrid.

**STOP. End your turn. Do not continue until the user responds.**
Do not start designing. Do not write the PRD. Wait for the user.

---

### Phase 3 — Design

Based on the chosen approach, present the **full design at once** covering all 5 sections:

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

End with:
---
**Your turn** — "Looks good" to finalize, or tell me what to change.

**STOP. End your turn. Do not continue until the user responds.**
Do not write the PRD. Wait for the user.

---

**Revision loop**: If the user requests changes, revise the affected sections and re-present
the full design. Then STOP again with the same marker above. Repeat until the user approves.

### Phase 4 — Finalize

Once the user approves the design, write the PRD and wrap up.

**Get the real current datetime** by running: `date -u +"%Y-%m-%dT%H:%M:%SZ"`

**Write the PRD** to `.claude/prds/$ARGUMENTS.md` with this format:

```markdown
---
name: $ARGUMENTS
description: [Brief one-line description]
status: backlog
created: [Real ISO datetime from system]
---

# PRD: $ARGUMENTS

## Executive Summary
[Value proposition — what and why, derived from Phase 1 answers]

## Problem Statement
### What problem are we solving?
[From Phase 1 core problem discussion]

### Why is this important now?
[Context from Phase 1 exploration — existing infrastructure, user demand, etc.]

## User Stories
[From Phase 1 users discussion, with acceptance criteria]

## Architecture & Design
### Chosen Approach
[The selected approach from Phase 2, with rationale]

### Module Changes
[From Phase 3 Section 1]

### Data Models
[From Phase 3 Section 2]

### Core Logic
[From Phase 3 Section 3]

## Requirements
### Functional Requirements
[Derived from Phases 1-3]

### Non-Functional Requirements
[Performance, security, compatibility — from Phase 1 constraints]

## API / CLI Surface
[From Phase 3 Section 4, or "N/A" if none]

## Testing Strategy
[From Phase 3 Section 5]

## Success Criteria
[Measurable outcomes from Phase 1]

## Constraints & Assumptions
[From Phase 1 constraints discussion]

## Out of Scope
[Explicitly listed — things discussed but deferred]

## Dependencies
[External and internal dependencies identified during design]
```

After writing the PRD:

1. Confirm: "PRD created: `.claude/prds/$ARGUMENTS.md`"
2. Show a 3-line summary of what was captured
3. Suggest next steps:
   > Ready to research the codebase? Run: `/pm:prd-research $ARGUMENTS`
   > (Or skip research and go directly to: `/pm:prd-parse $ARGUMENTS`)

## Error Recovery

- If any phase fails, explain what went wrong and how to fix it
- Never leave partial or corrupted files
- If the user abandons mid-session, do not write the PRD

## Tips

- Prefer concrete examples over abstract descriptions
- Reference existing code and patterns from the codebase when proposing approaches
- Keep the PRD focused — if scope creeps, suggest splitting into multiple PRDs
- The PRD should be detailed enough that `/pm:prd-parse` can decompose it into an epic without ambiguity
