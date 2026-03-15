---
allowed-tools: Bash, Read, Glob, Grep, Task
---

# Context7 — Library Verification & PRD Audit

Two modes: **code verification** (default) and **PRD audit** (`prd` subcommand).

## Usage

```
/context7 [target]              # Code mode — verify library mappings
/context7 prd [name]            # PRD mode — audit PRD claims against codebase
/context7 prd [name] --full     # PRD mode + Context7 MCP for library API claims
```

---

## Mode 1: Code Verification (default)

Verify that data structures in staged/changed files correctly map to external library APIs using Context7.

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
    2. Identify every place where external library output is accessed or mapped
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

    VERIFIED CORRECT:
    - {file}:{line} — {structure/field}: matches {library} docs

    MISMATCHES FOUND:
    - {file}:{line} — {structure/field}
      Code assumes: {what the code does}
      Library docs: {what Context7 says}
      Fix: {specific correction}

    COULD NOT VERIFY:
    - {file}:{line} — {structure/field}: {reason}

    RECOMMENDATIONS:
    1. {priority fixes}

    IMPORTANT: Only report genuine mismatches. Do not flag code as wrong
    unless Context7 docs clearly contradict what the code assumes.
    Limit Context7 calls to 3 per library (resolve + up to 2 queries).
```

### 4. Report Results

Present the agent's findings directly to the user. When mismatches are found, apply the fixes described in the report, stage the fixed files, and report.

### 5. Write Verification Stamp

1. Compute staged diff hash: `git diff --staged | git hash-object --stdin`
2. Write the hash to `.claude/.context7-stamp` (single line, no trailing newline)

---

## Mode 2: PRD Audit (`prd` subcommand)

Audit technical claims in PRD files against the actual codebase. Catches wrong file paths, misnamed model fields, stale dependency versions, boundary violations, and incorrect library API assumptions before PRD-to-epic conversion.

### Step 1: Resolve PRD Scope

- `prd` → All `.md` files in `.claude/prds/`
- `prd <name>` → `.claude/prds/<name>.md` (append `.md` if missing)
- Extract `--full` flag from anywhere in args (enables library API verification in P7)

For each PRD:
1. Read the file
2. Parse YAML frontmatter for `name` and `status` (`planned` | `researched` | `in-progress` | `completed`). Default to `planned` if missing.

### Step 2: Extract Claims

Scan the full PRD text and extract claims by category:

**[P1] FILE PATHS** — Backtick-quoted paths ending in `.py`, `.sql`, `.md`, etc.
Normalize to `src/options_arena/` prefix if not already present. Also capture migration
files (`data/migrations/`), test files, config files.

**[P2] MODEL FIELDS** — Patterns like `ModelName.field_name`, "`field_name: type`" in
model context, or "adds `field_name` field to `ModelName`". Extract model name, field
name, and expected type if stated.

**[P3] ENUM VARIANTS** — Patterns like "adds `VARIANT`", "`EnumClass.VARIANT`", or
"gains `VARIANT`". Extract enum class and variant name.

**[P4] IMPORT BOUNDARIES** — Phrases like "imports from X only", "never imports Y",
"X cannot access Y". Extract source module, allowed/disallowed target, direction.

**[P5] DEPENDENCIES** — Package names with version constraints (e.g., "scipy >= 1.17",
"no new dependencies", "uses existing pandas"). Extract package name and constraint.

**[P6] ARCHITECTURE** — Claims about field counts, base classes, function existence,
method signatures, class inheritance, weight values, constants.

**[P7] LIBRARY APIs** — References to external library functions or behavior (e.g.,
"`scipy.optimize.brentq`", "`yfinance.Ticker.options`", "`numpy.polynomial`").
Tagged for `--full` mode Context7 verification.

Report:
```
Claims extracted: {N} ([P1]: {n1}, [P2]: {n2}, ..., [P7]: {n7})
```

### Step 3: Verify Claims

**[P1] FILE PATHS** — Use `Glob` to check existence. `src/options_arena/` prefix if needed.
- Exists → FOUND
- Missing → NOT_FOUND

**[P2] MODEL FIELDS** — Use `Grep` to find the model class, then check field exists with expected type.
- Field + type match → FOUND
- Field exists, different type → MISMATCH
- Field not found → NOT_FOUND

**[P3] ENUM VARIANTS** — Use `Grep` to search for the variant in the expected enum class (typically `models/enums.py`).
- Found → FOUND
- Missing → NOT_FOUND

**[P4] IMPORT BOUNDARIES** — Use `Grep` to scan imports in the target module.
- "must not import X": no matches → COMPLIANT, matches → VIOLATION
- "imports X only": verify all imports, extra → VIOLATION

**[P5] DEPENDENCIES** — Use `Read` on `pyproject.toml`. Check `[project.dependencies]` and `[project.optional-dependencies]`.
- Found with compatible version → MATCH
- Found with incompatible version → MISMATCH
- Not found when expected → NOT_FOUND

**[P6] ARCHITECTURE** — Use `Read`/`Grep` on relevant source files.
- Claim matches → MATCH
- Contradicts → MISMATCH

**[P7] LIBRARY APIs** (only with `--full`) — Launch a verification agent via Task tool:

```markdown
Task:
  description: "Verify PRD library API claims via Context7"
  subagent_type: "general-purpose"
  prompt: |
    Verify these library API claims from a PRD using Context7 MCP.

    ## Claims to verify:
    {list of P7 claims with source text}

    ## For each claim:
    1. Call `resolve-library-id` for the library
    2. Call `query-docs` to verify the specific API claim
    3. Report: VERIFIED (matches), MISMATCH (differs), or SKIPPED (not in Context7)

    For MISMATCH, include what the PRD claims vs what Context7 documents.
    Limit to 3 Context7 calls per library.
```

Without `--full`, report all P7 claims as SKIPPED: "use `--full` for library API verification".

### Step 4: Interpret Results by PRD Status

NOT_FOUND severity depends on PRD `status`:

| PRD Status | NOT_FOUND meaning | Severity |
|------------|-------------------|----------|
| `planned` / `researched` | Features not built yet | **INFO** |
| `in-progress` | May or may not exist | **WARN** |
| `completed` | Should exist — something is wrong | **FAIL** |

MISMATCH and VIOLATION are always **FAIL** (PRD contradicts existing code).
FOUND, MATCH, COMPLIANT, VERIFIED are always **PASS**.

### Step 5: Report

Per-PRD report:

```
PRD AUDIT: {name} (status: {status})
=========
Claims: {N} extracted

[P1] FILE PATHS         {found}/{total}     {PASS|FAIL|INFO|WARN}
[P2] MODEL FIELDS       {found}/{total}     {PASS|FAIL|INFO|WARN}
[P3] ENUM VARIANTS      {found}/{total}     {PASS|FAIL|INFO|WARN}
[P4] IMPORT BOUNDARIES  {pass}/{total}      {PASS|FAIL}
[P5] DEPENDENCIES       {match}/{total}     {PASS|FAIL}
[P6] ARCHITECTURE       {match}/{total}     {PASS|FAIL|INFO|WARN}
[P7] LIBRARY APIs       {verified}/{total}  {PASS|FAIL|SKIPPED}

VERDICT: {PASS | FAIL | INFO}
```

For FAIL or WARN lines, append details (which files missing, which fields mismatched).

When auditing multiple PRDs, output one block per PRD, then:

```
SUMMARY: {N} PRDs audited — {pass} PASS, {fail} FAIL, {info} INFO
```

Verdict rules:
- Any MISMATCH or VIOLATION → **FAIL**
- NOT_FOUND in `completed` PRD → **FAIL**
- NOT_FOUND only in `in-progress` (no other FAILs) → **WARN**
- NOT_FOUND only in `planned`/`researched` (no FAILs) → **INFO**
- All FOUND/MATCH/COMPLIANT → **PASS**

---

## Error Handling

- No changed files and no target → "No changes found. Specify a file or library to verify."
- No `.py` files in changes → "No Python files in changes. Nothing to verify."
- Context7 unavailable → "Context7 unreachable. Mark assumptions as unverified per .claude/guides/context7-verification.md"
- PRD not found → "PRD not found: .claude/prds/{name}.md"
- No PRDs in directory → "No PRDs found in .claude/prds/"

## Important Notes

- This command is **read-only** in PRD mode — never modifies PRDs or source code
- Code mode may apply fixes when mismatches are found
- PRD audit catches stale claims *before* epic decomposition — run it after writing/editing a PRD
- Library API verification (P7) requires `--full` flag and Context7 MCP server
