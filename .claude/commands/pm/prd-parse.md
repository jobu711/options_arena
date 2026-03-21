---
allowed-tools: Bash, Read, Write, LS, Agent
---

# PRD Parse

Convert PRD to technical implementation epic(s). Automatically detects whether the PRD
requires a single epic or multiple epics and creates the appropriate structure.

## Usage
```
/pm:prd-parse <feature_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Before proceeding, complete these validation steps.
Do not bother the user with preflight checks progress ("I'm not going to ..."). Just do them and move on.

### Validation Steps
1. **Verify <feature_name> was provided as a parameter:**
   - If not, tell user: "Feature name not provided. Run: /pm:prd-parse <feature_name>"
   - Stop execution if <feature_name> was not provided

2. **Verify PRD exists:**
   - Check if `.claude/prds/$ARGUMENTS.md` exists
   - If not found, tell user: "PRD not found: $ARGUMENTS. Create it with: /pm:prd-new $ARGUMENTS"
   - Stop execution if PRD doesn't exist

3. **Validate PRD frontmatter:**
   - Verify PRD has valid frontmatter with: name, description, status, created
   - If frontmatter is invalid or missing, tell user what's missing
   - Stop execution if invalid

4. **Check for existing epic(s):**
   - Check if `.claude/epics/$ARGUMENTS/epic.md` already exists
   - Also check for child epic directories matching `$ARGUMENTS-*`
   - If any exist, list them and ask: "Epic(s) for '$ARGUMENTS' already exist. Overwrite? (yes/no)"
   - Only proceed with explicit 'yes' confirmation

5. **Verify directory permissions:**
   - Ensure `.claude/epics/` directory exists or can be created

6. **Check for research (non-blocking):**
   - Check if `.claude/epics/$ARGUMENTS/research.md` exists
   - If missing, warn: "No research found. Consider running /pm:prd-research $ARGUMENTS first."
   - Continue regardless

## Instructions

You are a technical lead converting a Product Requirements Document into a detailed
implementation plan for: **$ARGUMENTS**

### 1. Read the PRD
- Load the PRD from `.claude/prds/$ARGUMENTS.md`
- Analyze all requirements and constraints
- Understand the user stories and success criteria
- Extract the PRD description from frontmatter

### 2. Technical Analysis
- If `.claude/epics/$ARGUMENTS/research.md` exists, read it first and incorporate findings
- Identify architectural decisions needed
- Map functional requirements to technical components
- Identify integration points and dependencies
- Look for ways to simplify and leverage existing functionality

### 3. Determine Single vs Multi-Epic

Analyze the PRD to decide whether it needs **one epic** or **multiple epics**.

**Use multiple epics when ANY of these are true:**
- The PRD explicitly defines named phases/epics in an "Implementation Phasing" section
- The PRD spans 3+ modules with distinct, separately-shippable milestones
- The total estimated work exceeds ~15 tasks (single epics cap at 10 tasks)
- There are clear dependency chains where later work cannot begin until earlier work ships
  (e.g., "models first, then agents, then wiring, then cutover")

**Use a single epic when:**
- The PRD fits comfortably in ≤10 tasks
- All work lands in 1-2 modules
- No distinct shippable milestones — it's one cohesive unit

**Present the decision to the user before proceeding:**
```
Analyzed PRD: $ARGUMENTS

[Single-epic / Multi-epic] approach recommended.
Reason: {1-2 sentence justification}

{If multi-epic:}
Proposed epics ({count}):
  1. $ARGUMENTS-{suffix} — {one-line scope}
  2. $ARGUMENTS-{suffix} — {one-line scope}
  ...
Dependency chain: {A} -> {B} -> {C} (or "all parallel", etc.)

Proceed? (yes/no/adjust)
```

If the user says "adjust", ask what they'd like changed and revise the plan.
Only proceed with explicit confirmation.

---

## Path A: Single Epic

When the decision is **single epic**, follow this path.

### A.1 Create Epic File

Create `.claude/epics/$ARGUMENTS/epic.md`:

```markdown
---
name: $ARGUMENTS
status: backlog
created: [Current ISO date/time]
progress: 0%
prd: .claude/prds/$ARGUMENTS.md
github: [Will be updated when synced to GitHub]
---

# Epic: $ARGUMENTS

## Overview
Brief technical summary of the implementation approach

## Architecture Decisions
- Key technical decisions and rationale
- Design patterns to use

## Technical Approach
### Backend
- Data models, services, business logic

### Frontend (if applicable)
- UI components, state management

## Task Breakdown Preview
High-level task categories that will be created:
- [ ] Category 1: Description
- [ ] Category 2: Description
- [ ] etc.

## Dependencies
- External and internal dependencies
- Prerequisite work

## Success Criteria (Technical)
- Quality gates and acceptance criteria

## Estimated Effort
- Overall estimate
- Critical path items
```

### A.2 Continue to Finalization (Step 7)

---

## Path B: Multi-Epic

When the decision is **multiple epics**, follow this path.

### B.1 Determine Epic Names

Epic naming convention: `$ARGUMENTS-{short-suffix}`

Examples from PRD with epics A-D:
- `unified-agent-system-foundation`
- `unified-agent-system-desk-recommend`
- `unified-agent-system-orchestrator`
- `unified-agent-system-cutover`

If the PRD defines explicit epic/phase names, derive suffixes from those.
Keep suffixes short (1-3 words, kebab-case).

### B.2 Create Parent Epic

Create `.claude/epics/$ARGUMENTS/epic.md`:

```markdown
---
name: $ARGUMENTS
status: backlog
created: [Current ISO date/time]
progress: 0%
prd: .claude/prds/$ARGUMENTS.md
type: parent
child_epics:
  - $ARGUMENTS-suffix1
  - $ARGUMENTS-suffix2
  - $ARGUMENTS-suffix3
github: [Will be updated when synced to GitHub]
---

# Epic: $ARGUMENTS (Parent)

## Overview
Brief technical summary of the overall implementation approach.
This parent epic coordinates {N} child epics.

## Architecture Decisions
- Key technical decisions and rationale (shared across all child epics)
- Design patterns to use

## Child Epic Summary

| Epic | Scope | Dependencies | Est. Tasks |
|------|-------|-------------|------------|
| $ARGUMENTS-suffix1 | {scope} | None | {N} |
| $ARGUMENTS-suffix2 | {scope} | suffix1 | {N} |
| ... | ... | ... | ... |

## Dependency Graph

{ASCII diagram showing epic dependencies, e.g.:}
```
suffix1 --> suffix2 --> suffix3
              \--> suffix4 (parallel with suffix3)
```

## Success Criteria (Technical)
- Overall success criteria from the PRD

## Estimated Effort
- Total across all child epics
- Critical path
```

### B.3 Create Child Epics

For each child epic, create `.claude/epics/$ARGUMENTS-{suffix}/epic.md`:

```markdown
---
name: $ARGUMENTS-{suffix}
status: backlog
created: [Current ISO date/time]
progress: 0%
prd: .claude/prds/$ARGUMENTS.md
parent_epic: $ARGUMENTS
depends_on: []  # List of sibling epic names this depends on
github: [Will be updated when synced to GitHub]
---

# Epic: $ARGUMENTS-{suffix}

## Overview
What this child epic delivers and why it's a separate unit of work.

## Scope Boundary
### In Scope
- Specific deliverables for THIS epic only

### Out of Scope (handled by sibling epics)
- What is explicitly NOT in this epic

## Architecture Decisions
- Decisions specific to this epic (inherits parent decisions)

## Technical Approach
### Backend
- Data models, services, logic for this epic

### Frontend (if applicable)
- UI changes for this epic

## Task Breakdown Preview
- [ ] Category 1: Description
- [ ] Category 2: Description

## Dependencies
- Sibling epic dependencies (must ship first)
- External dependencies

## Success Criteria
- What "done" looks like for THIS epic
- Verification gates before next epic can start

## Estimated Effort
- Task count estimate
- Critical items
```

If the task count is clear and small, create child epics sequentially. If there are
many child epics (4+), use Agent tool to create them in parallel (max 3 concurrent):

```yaml
Agent:
  description: "Create child epic {suffix}"
  prompt: |
    Create the child epic file at .claude/epics/$ARGUMENTS-{suffix}/epic.md
    with the following content: {full epic content}

    Create the directory first if it doesn't exist.
```

### B.4 Copy Research to Child Epics (if applicable)

If `.claude/epics/$ARGUMENTS/research.md` exists, it stays with the parent.
Child epics reference it: "See parent epic research: `.claude/epics/$ARGUMENTS/research.md`"

### B.5 Continue to Finalization (Step 7)

---

## 7. Finalization (Both Paths)

### 7.1 Quality Validation

Before saving, verify:
- [ ] All PRD requirements are addressed (across all epics if multi-epic)
- [ ] No requirement falls through the cracks between child epic scope boundaries
- [ ] Dependencies are technically accurate
- [ ] Architecture decisions are justified

### 7.2 Update PRD Status

Update `.claude/prds/$ARGUMENTS.md` frontmatter `status:` to `planned`.
Preserve all other fields and content.

### 7.3 Write Checkpoint (best-effort)

Write `.claude/epics/$ARGUMENTS/checkpoint.json`. Failure does not fail the command.

If `checkpoint.json` already exists (e.g., from `/pm:prd-research`), read it first and
preserve `notes` and `blockers`. Update `phase`, `last_command`, `last_updated`, and
merge `completed_phases`.

```json
{
  "epic": "$ARGUMENTS",
  "phase": "planning",
  "last_command": "/pm:prd-parse $ARGUMENTS",
  "last_updated": "{current ISO datetime}",
  "completed_phases": ["prd-created", "planning"],
  "current_task": null,
  "tasks_completed": [],
  "tasks_in_progress": [],
  "blockers": [],
  "notes": ""
}
```

If `research.md` exists, include `"research"` in `completed_phases`.

For multi-epic, also write a checkpoint for each child epic directory:
```json
{
  "epic": "$ARGUMENTS-{suffix}",
  "phase": "planning",
  "last_command": "/pm:prd-parse $ARGUMENTS",
  "last_updated": "{current ISO datetime}",
  "completed_phases": ["prd-created", "planning"],
  "parent_epic": "$ARGUMENTS",
  "current_task": null,
  "tasks_completed": [],
  "tasks_in_progress": [],
  "blockers": [],
  "notes": ""
}
```

### 7.4 Post-Creation Output

**Single epic:**
```
Epic created: .claude/epics/$ARGUMENTS/epic.md
  Task categories: {count}
  Key decisions: {1-2 bullet summary}
  Estimated effort: {estimate}

Next: /pm:epic-decompose $ARGUMENTS
```

**Multi-epic:**
```
Parent epic created: .claude/epics/$ARGUMENTS/epic.md
Child epics created ({count}):
  1. $ARGUMENTS-{suffix} — {scope} ({est_tasks} tasks)
  2. $ARGUMENTS-{suffix} — {scope} ({est_tasks} tasks)
  ...
Dependency chain: {summary}
Total estimated tasks: {sum}

Next: /pm:epic-decompose $ARGUMENTS-{first_suffix}
  (Decompose child epics individually, in dependency order)
```

## Downstream Workflow — Multi-Epic

After `prd-parse` creates multiple epics, the downstream commands work per-child-epic:

1. `/pm:epic-decompose $ARGUMENTS-suffix1` — decompose first child into tasks
2. `/pm:epic-sync $ARGUMENTS-suffix1` — sync to GitHub
3. `/pm:epic-start $ARGUMENTS-suffix1` — execute first child
4. `/pm:epic-merge $ARGUMENTS-suffix1` — merge first child
5. Repeat for next child epic in dependency order

The parent epic is a coordination artifact — it is never decomposed or started directly.
`/pm:epic-status $ARGUMENTS` shows the parent with rollup progress across children.

## Error Recovery

If any step fails:
- Clearly explain what went wrong
- If PRD is incomplete, list specific missing sections
- If multi-epic and partial creation fails, list which epics were created
- Never leave epics in an inconsistent state

## IMPORTANT:
- Single epics: aim for ≤10 tasks.
- Multi-epic: aim for ≤10 tasks per child epic.
- Identify ways to simplify. Leverage existing functionality over creating new code.
- Multi-epic is NOT the default — only use it when the PRD genuinely requires it.
