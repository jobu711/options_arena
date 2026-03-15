---
allowed-tools: Bash, Read, Glob, LS
---

# PRD Status

Show all PRDs (no argument) or detail for one PRD (with argument).

## Usage
```
/pm:prd-status
/pm:prd-status <feature_name>
```

## Instructions

### Mode 1: No argument — PRD List

Scan `.claude/prds/*.md`. For each, extract frontmatter: `title`, `status`, `created`, `updated`.

Check if each PRD has a linked epic: look for `.claude/epics/{prd_name}/epic.md`.

Output:

```
PRDs ({count}):

  Name              Status     Epic Linked   Updated
  ──────────────────────────────────────────────────────
  {name}            {status}   {yes/no}      {date}
  {name}            {status}   {yes/no}      {date}
  ...

Actions:
  Detail:  /pm:prd-status <name>
  New:     /pm:prd-new <feature>
  Parse:   /pm:prd-parse <name>
```

### Mode 2: With argument — PRD Detail

Read `.claude/prds/$ARGUMENTS.md` fully. Extract frontmatter + body.

Check for linked epic and its status:
```bash
test -f .claude/epics/$ARGUMENTS/epic.md && echo "Epic exists"
```

If epic exists, read its frontmatter for `status`, `progress`, `github`.

Output:

```
PRD: $ARGUMENTS
  Status: {status}
  Created: {date}  Updated: {date}

{If epic linked}:
  Epic: {epic_status} — {progress}% complete [#{github_issue}]

Summary:
  {First 5 lines of PRD body or executive summary section}

Sections:
  {List of ## headings in the PRD}

Actions:
  Edit:      /pm:prd-edit $ARGUMENTS
  Parse:     /pm:prd-parse $ARGUMENTS
  {If epic}: /pm:epic-status $ARGUMENTS
```

### Error Handling

- PRD not found: "PRD '$ARGUMENTS' not found in .claude/prds/. Run /pm:prd-status (no args) to list all."
- No PRDs exist: "No PRDs found. Start with: /pm:prd-new <feature>"
