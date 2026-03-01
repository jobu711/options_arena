---
allowed-tools: Bash, Read, Glob, Grep, Task
---

# Context7 Structure Verification

Verify that data structures in staged/changed files correctly map to external library APIs using Context7.

## Usage
```
/verify-structures [target]
```

Where `target` can be:
- Empty (verify structures in staged and unstaged changes)
- File path or glob pattern (verify specific files)
- Library name (verify all structures mapping to that library)

## Instructions

### 1. Identify Changed Files with External Library Mappings

Based on the argument provided:

- **No arguments** → Get changed files from `git diff --name-only` and `git diff --staged --name-only`. Filter to `.py` files under `src/`.
- **File path/glob** → Use the specified files directly.
- **Library name** → Search `src/` for files importing that library and narrow to changed files if any, otherwise check all importers.

### 2. Extract External Library Interfaces

For each file, identify code that maps external library output to typed structures:

**What to look for:**
- Pydantic models whose fields correspond to external API responses (yfinance `.info`, `.option_chain()`, FRED JSON, etc.)
- Service methods that parse library return values into typed models
- `pd.read_html()` / `pd.read_csv()` calls where column names come from external sources
- Direct attribute access on library objects (e.g., `ticker.info["regularMarketPrice"]`)
- Function calls with parameter names that must match library signatures

**Key libraries in this project:**
| Library | Typical mapping locations |
|---------|--------------------------|
| yfinance | `services/market_data.py`, `services/options_data.py` |
| pandas | `indicators/`, `services/universe.py` |
| scipy | `pricing/bsm.py`, `pricing/american.py` |
| pydantic-ai | `agents/` |
| httpx | `services/fred.py`, `services/health.py` |
| fastapi | `api/` |
| typer | `cli/` |
| rich | `cli/`, `reporting/` |
| pydantic-settings | `models/config.py` |

### 3. Launch Verification Agent

Use the Task tool with `subagent_type: general-purpose`:

```markdown
Task:
  description: "Verify structures via Context7"
  subagent_type: "general-purpose"
  prompt: |
    You are verifying that data structures in this Python project correctly map to
    external library APIs. Use Context7 (resolve-library-id → query-docs) to check
    each mapping.

    ## Files to verify:
    {list of files identified in step 1-2}

    ## For each file:

    1. Read the file
    2. Identify every place where external library output is accessed or mapped:
       - Field/attribute access on library objects
       - Column names assumed from DataFrames returned by libraries
       - Function/method parameters passed to library calls
       - Return type assumptions (DataFrame vs dict vs Series vs namedtuple)
    3. For each external library found, call `resolve-library-id` then `query-docs`
       to verify:
       - **Field names**: exact spelling and casing
       - **Return types**: what the function actually returns
       - **Parameter signatures**: required vs optional, defaults, valid values
       - **Nullable fields**: which can be None/NaN
    4. Compare what the code assumes vs what Context7 documents

    ## Output format:

    STRUCTURE VERIFICATION REPORT
    ==============================
    Files checked: {count}
    Libraries verified: {list}

    ✅ VERIFIED CORRECT:
    - {file}:{line} — {structure/field}: matches {library} docs

    ❌ MISMATCHES FOUND:
    - {file}:{line} — {structure/field}
      Code assumes: {what the code does}
      Library docs: {what Context7 says}
      Fix: {specific correction}

    ⚠️ COULD NOT VERIFY:
    - {file}:{line} — {structure/field}: {reason}

    📋 RECOMMENDATIONS:
    1. {priority fixes}

    If a library is not found in Context7, note it under COULD NOT VERIFY
    and move on. Do NOT make up verification results.

    IMPORTANT: Only report genuine mismatches. Do not flag code as wrong
    unless Context7 docs clearly contradict what the code assumes.
    Limit Context7 calls to 3 per library (resolve + up to 2 queries).
```

### 4. Report Results

Present the agent's findings directly to the user.

**All verified:**
```
✅ Structure verification passed — {count} mappings checked across {libraries}
```

**Mismatches found:**
```
❌ {count} structure mismatches found — fixing automatically

{full report from agent}
```

When mismatches are found, apply the fixes described in the report:
1. Edit the files to correct the mismatches
2. Stage the fixed files with `git add`
3. Report the fixes to the user

**No external mappings:**
```
No external library mappings found in changed files. Nothing to verify.
```

### 5. Write Verification Stamp

After verification completes (regardless of whether mismatches were found and fixed):

1. Compute staged diff hash: `git diff --staged | git hash-object --stdin`
2. Write the hash to `.claude/.context7-stamp` (single line, no trailing newline)
3. This stamp tells the pre-commit hook that verification ran for the current staged state

If mismatches were found and fixed:
1. The fixes were already applied and staged in step 4
2. Recompute the staged diff hash (it changed after staging fixes)
3. Write the updated stamp

The stamp is a single line containing the git hash-object of `git diff --staged` output.

## Error Handling

- No changed files and no target → "No changes found. Specify a file or library to verify."
- No `.py` files in changes → "No Python files in changes. Nothing to verify."
- Context7 unavailable → "⚠️ Context7 unreachable. Mark assumptions as unverified per .claude/guides/context7-verification.md"

## Important Notes

- This does NOT replace running tests — it catches mapping assumptions before they become bugs
- Focus on external library boundaries, not internal project structures
- The guide at `.claude/guides/context7-verification.md` documents known wrong assumptions
- Per project rules: code mapping external library output to models requires Context7 verification before commit
