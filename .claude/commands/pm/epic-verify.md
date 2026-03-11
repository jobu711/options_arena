---
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

# Epic Verify

Pre-merge verification gate: maps every PRD requirement to code + test evidence.

## Usage
```
/pm:epic-verify <epic_name>
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Do not bother the user with preflight checks progress. Just do them and move on.

1. **Verify epic name was provided:**
   - If not: "Epic name required. Usage: /pm:epic-verify <epic_name>"

2. **Locate epic directory:**
   - Check `.claude/epics/$ARGUMENTS/` first (active epic)
   - Then check `.claude/epics/archived/$ARGUMENTS/` (archived epic)
   - If not found: "Epic not found: $ARGUMENTS. Check available epics with: ls .claude/epics/"
   - Set `$EPIC_DIR` to the found path

3. **Locate PRD:**
   - Read `epic.md` frontmatter `prd:` field to find PRD path
   - If no `prd:` field, try `.claude/prds/$ARGUMENTS.md`
   - If no PRD found: "No PRD found for epic. Cannot verify without requirements source."

## Instructions

### 1. Extract Requirements

Read the PRD file and all task files to build a requirements list.

**From PRD**, extract:
- Functional requirements (bullet points under "Requirements", "Functional Requirements", or similar headings)
- Non-functional requirements (NFRs) under "Non-Functional Requirements" or "Constraints"
- Success criteria under "Success Criteria" or "Definition of Done"
- User story acceptance criteria (items after "Given/When/Then" or "- [ ]" checklists)

**From task files** (`[0-9]*.md` in `$EPIC_DIR`), extract:
- `name:` from frontmatter (task name)
- `status:` from frontmatter (task status)
- `github:` from frontmatter (issue URL — extract issue number)
- `test_files:` from frontmatter (list of test file paths)
- Acceptance criteria (`- [ ]` or `- [x]` checklists under "Acceptance Criteria")

Assign each requirement a sequential ID: `REQ-001`, `REQ-002`, etc.
Assign each acceptance criterion an ID: `AC-{issue_number}-{seq}` (e.g. `AC-376-01`).

### 2. Code Evidence Sweep

For each requirement and acceptance criterion, extract searchable keywords (function names, model names, config fields, class names) and search `src/options_arena/` for evidence.

Use Grep to search for each keyword. Record file:line matches.

Categorize each search:
- **Found**: at least one file:line match in `src/`
- **Not found**: no matches (may need manual verification)

### 3. Test File Verification

For each task's `test_files` from frontmatter:
- Glob the path to verify the test file exists
- Grep for `def test_` to count test functions in each file

Build a test inventory:
- Total test files referenced across all tasks
- Total test functions found
- Any missing test files (referenced but not found on disk)

### 4. Run Tests

Run tests for all discovered test files:
```bash
uv run pytest {space_separated_test_files} -v --tb=short 2>&1 | tail -80
```

If no test files found, run critical-tier tests:
```bash
uv run pytest -m critical -q 2>&1 | tail -20
```

Record: total tests, passed, failed, errors, skipped.

### 5. Git Traceability

For each task with a `github:` issue number, check for commits referencing that issue:
```bash
git log --all --oneline --grep="#{issue_number}" 2>/dev/null | head -10
```

Record commit count per task. Flag tasks with zero commits as "no commit trace".

### 6. Build Traceability Matrix

Categorize each requirement/AC:

| Status | Criteria |
|--------|----------|
| **PASS** | Code evidence found AND associated tests pass |
| **WARN** | Code found but no test, OR test exists but failed, OR no commit trace |
| **FAIL** | No code evidence found at all |
| **SKIP** | Not grep-verifiable (performance NFRs, UX requirements, manual-only checks) |

Compute coverage: `pass_count / (total - skip_count) * 100`

### 7. Write Verification Report

Get REAL current datetime by running the appropriate command for the platform.

Write `$EPIC_DIR/verification-report.md`:

```markdown
---
epic: {epic_name}
verified: {current ISO datetime}
status: {PASS if no FAIL items, WARN if any WARN, FAIL if any FAIL}
coverage: {coverage percentage}
total_requirements: {count}
passed: {count}
warned: {count}
failed: {count}
skipped: {count}
---

# Verification Report: {epic_name}

## Summary

- **Coverage**: {pass}/{total verifiable} requirements verified ({coverage}%)
- **Test Results**: {passed}/{total} tests passed
- **Commit Traces**: {traced}/{total_tasks} tasks have commit evidence

## Traceability Matrix

| ID | Requirement | Code Evidence | Test Evidence | Commits | Status |
|----|------------|---------------|---------------|---------|--------|
| REQ-001 | {text} | {file:line or "none"} | {test file + count or "none"} | {count} | PASS/WARN/FAIL/SKIP |
| AC-376-01 | {text} | {file:line or "none"} | {test file + count or "none"} | {count} | PASS/WARN/FAIL/SKIP |

## Test Results

{pytest output summary}

## Risk Flags

{List any FAIL or WARN items with explanation of why they couldn't be verified}

## Overrides

| ID | Original Status | Override | Reason |
|----|----------------|----------|--------|
{filled in by interactive step}
```

### 8. Interactive Override (if needed)

If any FAIL or WARN items exist:
- Display them to the user
- Ask for each: "Mark as verified manually, descoped, or leave as-is?"
  - **Verified manually**: change status to PASS, record reason in Overrides table
  - **Descoped**: change status to SKIP, record reason in Overrides table
  - **Leave as-is**: keep original status

Update the report file with any overrides. Recalculate coverage.

### 9. Update Checkpoint

If `$EPIC_DIR/checkpoint.json` exists:
- Read it
- Add `"verified"` to `completed_phases` array if not already present
- Update `last_updated` and `last_command`
- Write it back

### 10. Output

```
Verification complete: $ARGUMENTS

  Coverage: {pass}/{total verifiable} ({coverage}%)
  Status: {PASS/WARN/FAIL}
  Tests: {passed}/{total} passed
  Commits: {traced}/{total_tasks} tasks traced
  Report: $EPIC_DIR/verification-report.md

  {If FAIL}: Items need attention before merge.
  {If WARN}: Warnings present — review report before merge.
  {If PASS}: Ready for merge: /pm:epic-merge $ARGUMENTS

Next: /pm:epic-merge $ARGUMENTS
```

## Error Recovery

- If PRD parsing finds no requirements, warn and fall back to task ACs only
- If test run fails to start (missing deps), record "test run failed" and continue
- If git log fails, skip traceability and note it in report
- Report is always written, even if incomplete — partial verification is better than none
