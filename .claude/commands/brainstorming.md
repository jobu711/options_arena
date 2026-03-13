---
allowed-tools: Read, Glob, Grep, Bash, Write, Edit, Agent, TaskCreate, TaskUpdate, TaskList
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

Help turn ideas into fully formed designs and PRDs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to
refine the idea. Once you understand what you're building, present the design and get user
approval.

## Usage
```
/brainstorming <feature_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

<HARD-GATE>
Do NOT write any implementation code, source files, tests, or config changes until you have
presented a design and the user has approved it. The ONLY file you create is the PRD at the
end. If the user asks you to start coding, say: "Let's finish the design first —
implementation comes after `/pm:prd-research` or `/pm:prd-parse`."

This applies to EVERY feature regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every feature goes through this process. A single endpoint, a config change, a new CLI flag —
all of them. "Simple" features are where unexamined assumptions cause the most wasted work.
The design can be short (a few sentences for truly simple features), but you MUST present it
and get approval.

## CRITICAL: Tool Prohibition

**NEVER use `AskUserQuestion` during this skill.** This is a hard rule with no exceptions.
The `AskUserQuestion` tool auto-skips and hallucinates answers. Instead, use natural
conversation turns — output your text, then STOP and wait for the user's next message.

**NEVER use `EnterPlanMode` or `ExitPlanMode`.** This skill IS the planning process.

## CRITICAL: Conversation Turn Discipline

This skill uses **natural conversation turns** for ALL user interaction:
1. You output text (questions, proposals, designs)
2. You **STOP generating** — end your turn completely
3. The user responds in their next message
4. You continue based on their response

There are **multiple mandatory stop points**. At each one you MUST:
- End your message with the stop marker (shown in each phase)
- **Actually stop generating** — produce NO further tokens
- Do NOT continue to the next phase under any circumstances
- Wait for the user's next message before proceeding

**One question at a time.** Do not overwhelm with multiple questions in one message.
If a topic needs more exploration, break it into multiple conversation turns. Prefer
multiple choice questions when possible, but open-ended is fine too.

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** — check files, docs, recent commits
2. **Ask clarifying questions** — one at a time, understand purpose/constraints/success criteria
3. **Propose 2-3 approaches** — with trade-offs and your recommendation
4. **Present design** — in sections scaled to complexity, get user approval
5. **Write PRD** — save to `.claude/prds/$ARGUMENTS.md`
6. **Spec review** — dispatch code-reviewer agent to verify PRD completeness
7. **User reviews PRD** — ask user to review before proceeding
8. **Suggest next steps** — `/pm:prd-research` or `/pm:prd-parse`

Create these tasks at the start using TaskCreate. Update status as you progress.

## Process Flow

```
Explore context → Ask questions (one at a time, multiple turns)
    → Propose approaches → User picks one
    → Present design sections → User approves (or revision loop)
    → Write PRD → Spec review → User review → Done
```

## Phase 1 — Discover

### Preflight (silent — do not narrate)

1. **Validate feature name format:**
   - Must contain only lowercase letters, numbers, and hyphens
   - Must start with a letter
   - If invalid: "Feature name must be kebab-case (lowercase letters, numbers, hyphens).
     Examples: user-auth, payment-v2, notification-system"

2. **Check for existing PRD:**
   - Check if `.claude/prds/$ARGUMENTS.md` already exists
   - If it exists, tell the user: "PRD '$ARGUMENTS' already exists. Let me know if you
     want to overwrite it, or use a different name. You can also run
     `/pm:prd-parse $ARGUMENTS` to create an epic from the existing PRD."
   - **STOP and wait for the user's response before continuing.**

3. **Verify directory structure:**
   - Check if `.claude/prds/` directory exists; create if not

### Context Exploration (silent — do not narrate individual steps)

- Read `CLAUDE.md`, `.claude/context/progress.md`, `.claude/context/system-patterns.md`
- Glob for files related to the feature name (`$ARGUMENTS`)
- Check recent git commits (`git log --oneline -20`)
- Scan existing PRDs in `.claude/prds/` for related work
- Look at open GitHub issues if relevant (`gh issue list` if available)

### Present Findings

Summarize what you found in 3-5 bullet points:
> Based on the codebase, here's what I see:
> - The project already has X which relates to this feature
> - There's existing infrastructure in `module/` that could be leveraged
> - No prior PRD or epic covers this area

### Ask First Question

After presenting findings, ask your **first clarifying question**. Pick the most important
unknown — usually the core problem or purpose. Format as a clear question, with multiple
choice options when possible:

> **What specific problem does this solve?**
> - A) [concrete option based on context]
> - B) [another option]
> - C) Something else (describe it)

End with:

---
**Your turn.**

**STOP HERE. Do not generate another token. Wait for the user's response.**

---

### Subsequent Questions (one per turn)

After the user responds, ask the **next** clarifying question. Cover these areas across
multiple turns (skip any already answered):

- **Scope**: How large should the first version be? (Minimal MVP / Moderate / Full-featured)
- **Constraints**: Any hard constraints? (timeline, tech stack, compatibility)
- **Success criteria**: How will we know this works?
- **Edge cases**: Any specific scenarios to handle?

**Each question gets its own turn.** Ask one, STOP, wait for response, then ask the next.
When you have enough information to propose approaches (typically 2-4 questions), move to
Phase 2. You do NOT need to ask every question — skip what's already clear.

End each question turn with:

---
**Your turn.**

**STOP HERE. Do not generate another token. Wait for the user's response.**

---

## Phase 2 — Propose

Once you have sufficient context, present 2-3 distinct approaches:

```
### Approach A: [Name]
**How it works**: [2-3 sentences]
**Pros**: [Bullet list]
**Cons**: [Bullet list]
**Complexity**: Low / Medium / High
**Fits existing architecture**: Yes / Partially / No
```

Lead with your recommended option and explain why:
> **Recommended: Approach B** — [one sentence why]

End with:

---
**Your turn** — pick an approach (A, B, C) or suggest a hybrid.

**STOP HERE. Do not generate another token. Wait for the user's response.**
Do not start designing. Do not write the PRD.

---

## Phase 3 — Design

Based on the chosen approach, present the design. Scale each section to its complexity —
a few sentences if straightforward, more detail if nuanced.

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

**STOP HERE. Do not generate another token. Wait for the user's response.**
Do not write the PRD.

---

**Revision loop**: If the user requests changes, revise the affected sections and re-present.
Then STOP again with the same marker. Repeat until the user says it's good.

## Phase 4 — Finalize

Once the user approves the design, write the PRD and wrap up.

### Write the PRD

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

### Spec Review

After writing the PRD, dispatch a code-reviewer agent to verify completeness:

```
Agent tool (code-reviewer):
  prompt: |
    Review the PRD at `.claude/prds/$ARGUMENTS.md` for completeness.
    Check for: TODOs, placeholders, "TBD", incomplete sections, internal
    contradictions, missing edge cases, ambiguous requirements, YAGNI
    violations, scope creep. Report status: Approved or Issues Found.
```

If issues are found, fix them and re-dispatch (max 3 iterations, then surface to user).

### User Review Gate

After the spec review passes, ask the user to review:

> PRD written to `.claude/prds/$ARGUMENTS.md`. Please review it and let me know if
> you want any changes before we proceed.

**STOP HERE. Wait for the user's response.**

If they request changes, make them and re-run the spec review. Only proceed once approved.

### Suggest Next Steps

Once the user approves:

1. Confirm: "PRD finalized: `.claude/prds/$ARGUMENTS.md`"
2. Show a 3-line summary of what was captured
3. Suggest next steps:
   > Ready to research the codebase? Run: `/pm:prd-research $ARGUMENTS`
   > (Or skip research and go directly to: `/pm:prd-parse $ARGUMENTS`)

## Working in an Existing Codebase

- Explore the current structure before proposing changes. Follow existing patterns.
- Where existing code has problems that affect the work, include targeted improvements
  as part of the design — not unrelated refactoring.
- Reference specific files, models, and patterns from the codebase when proposing approaches.

## Key Principles

- **One question at a time** — don't overwhelm with multiple questions
- **Multiple choice preferred** — easier to answer than open-ended
- **YAGNI ruthlessly** — remove unnecessary features from all designs
- **Explore alternatives** — always propose 2-3 approaches before settling
- **Incremental validation** — present design, get approval before moving on
- **Scale to complexity** — simple features get short designs, complex get thorough ones
- **Be concrete** — reference existing code, not abstract descriptions

## Error Recovery

- If any phase fails, explain what went wrong and how to fix it
- Never leave partial or corrupted files
- If the user abandons mid-session, do not write the PRD
- Keep the PRD focused — if scope creeps, suggest splitting into multiple PRDs
- The PRD should be detailed enough that `/pm:prd-parse` can decompose it into an epic
  without ambiguity
