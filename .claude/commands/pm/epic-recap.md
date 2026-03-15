---
allowed-tools: Bash, Read, Glob, Grep, Write, Agent
---

# Epic Recap

Generate a browser-based visual walkthrough of what was built in an epic.

## Usage
```
/pm:epic-recap <epic_name>
/pm:epic-recap <epic_name> --diagrams
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Do not narrate preflight steps. Just do them.

1. **Validate arguments:**
   - Extract `<epic_name>` from `$ARGUMENTS` (first word)
   - Check for `--diagrams` flag in `$ARGUMENTS`
   - If no epic name: "Usage: `/pm:epic-recap <epic_name> [--diagrams]`"

2. **Locate epic directory:**
   - Check `.claude/epics/$EPIC_NAME/` first (active/completed)
   - Then check `.claude/epics/archived/$EPIC_NAME/` (archived)
   - If not found: "Epic not found: `$EPIC_NAME`. Run `/pm:epic-list` to see available epics."
   - Set `$EPIC_DIR` to the found path

3. **Verify epic.md exists:**
   - Read `$EPIC_DIR/epic.md`
   - If missing: "Epic directory exists but `epic.md` is missing."

## Instructions

### 1. Gather Epic Data

Read these files (skip any that don't exist):

**Epic metadata:**
- `$EPIC_DIR/epic.md` — overview, architecture decisions, technical approach, status
- All `$EPIC_DIR/[0-9]*.md` — task files (use Glob pattern `$EPIC_DIR/[0-9]*.md`)
- `$EPIC_DIR/checkpoint.json` — phase tracking
- `$EPIC_DIR/retro.md` — retrospective metrics (if exists)
- PRD file path from `epic.md` frontmatter `prd:` field — read if it exists

**Git history:**

Run these commands to gather facts:

```bash
# Total commits on epic branch (if branch exists)
git log --oneline master..$EPIC_NAME 2>/dev/null | wc -l

# Files changed summary
git diff --stat master...$EPIC_NAME 2>/dev/null

# Per-task commits (for each issue number found in task files)
git log --all --oneline --grep="#<issue_number>" 2>/dev/null
```

If the epic branch doesn't exist (already merged), try:
```bash
# Search by epic name in commit messages
git log --all --oneline --grep="$EPIC_NAME" 2>/dev/null | head -30

# Search by issue numbers from task files
git log --all --oneline --grep="#<issue_number>" 2>/dev/null
```

### 2. Generate Markdown Recap

Synthesize the gathered data into a **compact** markdown document. Be token-efficient — every
sentence should carry information. No filler.

**Required sections:**

```markdown
# Epic Recap: {epic_name}

## Executive Summary

{2-3 sentences: what was built and why. Pull from epic.md overview.}

## Problem → Solution

**Problem**: {1-2 sentences from PRD problem statement}

**Solution**: {1-2 sentences describing what was delivered}

## What Changed

{Group files by module. Show file count and line delta per module.}

| Module | Files Changed | Lines (+/-) |
|--------|--------------|-------------|
| models/ | 3 | +245 / -12 |
| pricing/ | 1 | +89 / -0 |
| ... | ... | ... |

**New files**: {list new files, one per line}

## Architecture Decisions

{Pull from epic.md "Architecture Decisions" section. For each decision, add a one-line
annotation: "Held up well", "Required adjustment", or "Not yet validated".}

## Task Breakdown

| # | Task | Issue | Status | Commits |
|---|------|-------|--------|---------|
| 1 | {name} | #{num} | {status} | {count} |

## Metrics

{Only if retro.md exists. Otherwise omit this section entirely.}

- **Duration**: {days} days
- **Effort**: {proxy_hours}h (estimation ratio: {ratio}x)
- **Quality**: {post_merge_fixes} post-merge fixes
```

**If `--diagrams` flag is set**, add these additional sections using Mermaid fenced blocks:

````markdown
## Data Flow

```mermaid
graph LR
    A[Phase 1: Universe] --> B[Phase 2: Scoring]
    B --> C[Phase 3: Options]
    C --> D[Phase 4: Persist]
    {Add nodes/edges specific to what this epic added or modified}
```

## Module Dependencies

```mermaid
graph TD
    {Show only modules touched by this epic and their dependency relationships}
```
````

Build the Mermaid diagrams from:
- The epic's "Technical Approach" / "Data Flow" sections in `epic.md`
- The git diff file list (which modules were touched)
- The architecture boundary table in `CLAUDE.md`

### 3. Render in Browser

Read the HTML template:
```
.claude/templates/recap.html
```

**Prepare the markdown for injection:**
- The template uses `{{MARKDOWN_CONTENT}}` as the placeholder
- The markdown will be placed inside a JavaScript template literal (backtick string)
- You MUST escape these characters in the markdown content:
  - Backticks (`` ` ``) → `\``
  - Dollar signs followed by `{` (`${`) → `\${`
  - Backslashes (`\`) → `\\`

**Write the final HTML:**
```bash
# Determine temp directory
TEMP_DIR=$(mktemp -d 2>/dev/null || echo "$TEMP/epic-recap-$$")
mkdir -p "$TEMP_DIR"
```

Use the Write tool to create `$TEMP_DIR/index.html` with the template content,
replacing `{{EPIC_NAME}}` with the epic name and `{{MARKDOWN_CONTENT}}` with the
escaped markdown content.

**Serve and open:**
```bash
# Find an available port
PORT=$(python -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")

# Open browser (cross-platform)
python -c "import webbrowser; webbrowser.open('http://localhost:$PORT')"

# Serve (this blocks until Ctrl+C)
cd "$TEMP_DIR" && python -m http.server $PORT --bind 127.0.0.1
```

Run the server command with `run_in_background: true` so the user can continue working.
Tell the user the URL and how to stop it.

### 4. Output

```
Epic recap: {epic_name}

  Browser: http://localhost:{port}
  Sections: {count} sections{, 2 diagrams if --diagrams}
  Source: {task_count} tasks, {commit_count} commits, {files_changed} files

  Press Ctrl+C in the terminal or stop the background task to shut down the server.
```

## Error Recovery

- If epic branch not found in git: use issue-number grep to find commits. If no commits found,
  show "No git history available" in the What Changed section and skip Metrics.
- If PRD file not found: omit the "Problem" half of "Problem → Solution", show only "Solution".
- If template file missing: show error "Template not found: `.claude/templates/recap.html`. Reinstall the template."
- If port binding fails: retry with a different random port (up to 3 attempts).
- If browser fails to open: print the URL and tell the user to open it manually.
