---
allowed-tools: Read, LS, Glob, Grep, Task
---

# PRD Research

Investigate the codebase before converting a PRD to an epic.

## Usage
```
/pm:prd-research <feature_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Before proceeding, complete these validation steps.
Do not bother the user with preflight checks progress ("I'm not going to ..."). Just do them and move on.

### Validation Steps
1. **Verify <feature_name> was provided as a parameter:**
   - If not, tell user: "❌ <feature_name> was not provided as parameter. Please run: /pm:prd-research <feature_name>"
   - Stop execution if <feature_name> was not provided

2. **Verify PRD exists:**
   - Check if `.claude/prds/$ARGUMENTS.md` exists
   - If not found, tell user: "❌ PRD not found: $ARGUMENTS. First create it with: /pm:prd-new $ARGUMENTS"
   - Stop execution if PRD doesn't exist

3. **Validate PRD frontmatter:**
   - Verify PRD has valid frontmatter with: name, description, status, created
   - If frontmatter is invalid or missing, tell user: "❌ Invalid PRD frontmatter. Please check: .claude/prds/$ARGUMENTS.md"

4. **Check for existing research:**
   - Check if `.claude/epics/$ARGUMENTS/research.md` already exists
   - If it exists, ask user: "⚠️ Research for '$ARGUMENTS' already exists. Overwrite? (yes/no)"
   - Only proceed with explicit 'yes' confirmation

5. **Verify directory structure:**
   - Ensure `.claude/epics/$ARGUMENTS/` directory exists or can be created
   - Create it if missing

## Instructions

You are a technical researcher investigating the codebase to prepare for implementing: **$ARGUMENTS**

### 1. Read the PRD
- Load the PRD from `.claude/prds/$ARGUMENTS.md`
- Extract all requirements, constraints, user stories, and success criteria
- Identify key technical areas the feature will touch

### 2. Parallel Codebase Investigation

Spawn 2-3 parallel Explore agents to investigate the codebase:

**Agent 1: Architecture & Existing Patterns**
```yaml
Task:
  description: "Research architecture for $ARGUMENTS"
  subagent_type: "Explore"
  prompt: |
    Investigate the codebase architecture relevant to: $ARGUMENTS

    PRD summary: {brief summary of requirements}

    Research tasks:
    1. Find modules that will be affected (Glob for relevant directories)
    2. Read CLAUDE.md files in those modules to understand constraints
    3. Identify existing design patterns that should be reused
    4. Check architecture boundaries in the root CLAUDE.md

    Return:
    - List of relevant modules with brief descriptions
    - Key patterns and conventions to follow
    - Architecture boundaries that constrain the implementation
```

**Agent 2: Existing Code & Conflicts**
```yaml
Task:
  description: "Research existing code for $ARGUMENTS"
  subagent_type: "Explore"
  prompt: |
    Search for existing code relevant to: $ARGUMENTS

    Key areas to search: {list of keywords from PRD}

    Research tasks:
    1. Grep for overlapping functionality (similar features, related functions)
    2. Identify files that will need modification
    3. Check for potential conflicts with existing code
    4. Look for reusable utilities, helpers, or patterns

    Return:
    - Files that will likely need modification
    - Existing code that can be reused or extended
    - Potential conflicts or breaking changes
```

**Agent 3: Data Models & Integration Points** (only if PRD involves models/APIs/services)
```yaml
Task:
  description: "Research models/APIs for $ARGUMENTS"
  subagent_type: "Explore"
  prompt: |
    Investigate data models and integration points for: $ARGUMENTS

    Research tasks:
    1. Find relevant Pydantic models in src/options_arena/models/
    2. Check existing API endpoints in src/options_arena/api/
    3. Review service layer for integration opportunities
    4. Check database migrations for schema context

    Return:
    - Relevant existing models and their fields
    - API endpoints that may need changes
    - Service layer integration points
    - Database schema considerations
```

### 3. Synthesize Findings

After all agents return, combine their findings into a structured research document.

### 4. Write Research Document

Create `.claude/epics/$ARGUMENTS/research.md`:

```markdown
# Research: $ARGUMENTS

## PRD Summary
Brief summary of what the PRD requires.

## Relevant Existing Modules
- `module/` — How it relates to this feature
- `module/` — How it relates to this feature

## Existing Patterns to Reuse
- Pattern 1: Where it's used, how to apply it here
- Pattern 2: Where it's used, how to apply it here

## Existing Code to Extend
- `path/to/file.py` — What exists, what needs changing
- `path/to/file.py` — What exists, what needs changing

## Potential Conflicts
- Conflict 1: Description and mitigation strategy
- Conflict 2: Description and mitigation strategy

## Open Questions
- Question 1: What needs clarification before implementation
- Question 2: What needs clarification before implementation

## Recommended Architecture
High-level implementation approach based on codebase research.

## Test Strategy Preview
- Existing test patterns found in relevant modules
- Test file locations and naming conventions
- Mocking strategies used for similar features

## Estimated Complexity
- S/M/L/XL with justification based on codebase analysis
```

### 5. Create Planning Lock

Create `.claude/epics/$ARGUMENTS/.planning-lock` to prevent premature code writes:
```
Planning phase active for epic: $ARGUMENTS
Created by: /pm:prd-research
Remove with: /pm:epic-decompose $ARGUMENTS
```

### 6. Write Checkpoint

Write `.claude/epics/$ARGUMENTS/checkpoint.json` with current state:
```json
{
  "epic": "$ARGUMENTS",
  "phase": "research",
  "last_command": "/pm:prd-research $ARGUMENTS",
  "last_updated": "[Current ISO date/time]",
  "completed_phases": ["prd-created", "research"],
  "current_task": null,
  "tasks_completed": [],
  "tasks_in_progress": [],
  "blockers": [],
  "notes": ""
}
```

Get REAL current datetime by running: `date -u +"%Y-%m-%dT%H:%M:%SZ"` (or PowerShell equivalent on Windows).

### 7. Post-Research

After successfully creating the research document:
1. Confirm: "✅ Research complete: .claude/epics/$ARGUMENTS/research.md"
2. Show summary:
   - Number of relevant modules identified
   - Key patterns to reuse
   - Open questions (if any)
   - Estimated complexity
3. Note: "Planning lock active — code writes to src/, tests/, web/ blocked until decomposition."
4. Suggest next step: "Ready to create implementation epic? Run: /pm:prd-parse $ARGUMENTS"

## Error Recovery

If any step fails:
- If agents fail, report what was gathered and continue with partial results
- If directory creation fails, tell user exact fix
- Never leave partial research that might mislead later steps

Focus on understanding the codebase deeply enough to make informed architecture decisions for "$ARGUMENTS".
