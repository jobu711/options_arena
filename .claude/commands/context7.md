---
allowed-tools: Bash, Read, Glob, Grep, Agent
description: Fast structural verification — tach + ast-grep + ruff on changed or specified files, or PRD claim audit
---

<role>
You are a fast structural verification tool. You run deterministic checks (tach, ast-grep, ruff,
optionally mypy) and report pass/fail. In PRD audit mode, you extract technical claims from PRD
markdown and verify them against the codebase. You never modify code — verification only.
</role>

<task>
Run structural checks on the target scope. Parse arguments to determine scope, depth, and mode.
</task>

<instructions>

## Step 1: Parse Arguments

The user's input after `/context7` determines scope, depth, and mode:

**Code-audit mode (default):**

| Input | Scope | Depth |
|-------|-------|-------|
| *(empty)* | Changed files (`git diff HEAD --name-only` + `git diff --staged --name-only`) | deterministic |
| `all` | Entire `src/` | deterministic |
| `<path>` (file or dir) | That path | deterministic |
| `--full` | Changed files | deterministic + mypy + audit agents |
| `--full all` | Entire `src/` | deterministic + mypy + audit agents |
| `--full <path>` | That path | deterministic + mypy + audit agents |

**PRD-audit mode** (when first non-flag arg is `prd`):

| Input | Scope | Mode |
|-------|-------|------|
| `prd` | All PRDs in `.claude/prds/` | prd-audit |
| `prd <name>` | `.claude/prds/<name>.md` | prd-audit |
| `prd --full` | All PRDs + Context7 MCP library API verification | prd-audit + library |
| `prd <name> --full` | Single PRD + Context7 MCP library API verification | prd-audit + library |

Extract `--full` flag first (present anywhere in args). Then check if first remaining arg is `prd`.
If so, enter PRD-audit mode (skip Steps 2-3, go to Steps 2a-2b). If second remaining arg exists,
it's the PRD name (without `.md` extension).

**Code-audit scope resolution** (non-`prd` mode):

For changed-files scope: run `git diff HEAD --name-only && git diff --staged --name-only`,
deduplicate, filter to `.py` files under `src/`. If no Python files changed:
```
No Python source changes detected. Scope: changed files (0 files).
Tip: Use `/context7 all` to check entire src/ or `/context7 <path>` for a specific target.
```
Then STOP (do not treat empty changeset as fatal — just inform and exit).

For `all` scope: target is `src/`.
For path scope: verify the path exists, use it directly.

Report the resolved scope:
```
Scope: {changed files (N files) | all (src/) | <path>}
```

## Step 2: Run Deterministic Checks

*Skip this step in PRD-audit mode — go to Step 2a.*

Run these three commands. Capture stdout+stderr and exit codes.

**[1] BOUNDARIES (tach)**
```bash
uv run tach check 2>&1; echo "EXIT:$?"
```
Result: PASS if exit code 0, FAIL if non-zero. If `tach` not found, WARN and continue.
Note: tach checks the whole project graph — not scoped to individual files.

**[2] STRUCTURE (ast-grep)**
```bash
ast-grep scan --config sgconfig.yml {target} 2>&1; echo "EXIT:$?"
```
Where `{target}` is the resolved scope path (file, directory, or `src/` for `all`).
For changed-files scope, pass each file: `ast-grep scan --config sgconfig.yml file1.py file2.py ...`
Result: PASS if no matches, FAIL if any rule matches. If `ast-grep` not found, WARN and continue.

**[3] LINT (ruff)**
```bash
uv run ruff check {target} 2>&1; echo "EXIT:$?"
```
Where `{target}` is the same resolved scope. For changed-files, pass the file list.
Result: PASS if exit code 0, FAIL if violations found.

Run all three commands (they're fast). Report results immediately.

## Step 2a: PRD Claim Extraction (PRD-audit mode only)

For each PRD in scope:

1. **Read the PRD file** using the Read tool.
2. **Parse frontmatter** for `name` and `status` (one of: `planned`, `researched`, `in-progress`, `completed`). Default to `planned` if missing.
3. **Extract claims** by category. Scan the full PRD text for these patterns:

**[P1] FILE PATHS** — Backtick-quoted paths ending in `.py` (e.g., `` `pricing/dispatch.py` ``, `` `models/greeks.py` ``). Normalize to `src/options_arena/` prefix if not already present. Also capture paths to migration files, config files, etc.

**[P2] MODEL FIELDS** — Patterns like `ModelName.field_name`, "`field_name: type`" in context of a model definition, or "adds `field_name` field to `ModelName`". Extract the model name, field name, and expected type if stated.

**[P3] ENUM VARIANTS** — Patterns like "adds `VARIANT`", "new enum value `VARIANT`", "`EnumClass.VARIANT`", or "gains `VARIANT`". Extract enum class and variant name.

**[P4] IMPORT BOUNDARIES** — Phrases like "imports from X only", "never imports Y", "X cannot access Y", "does not depend on Z". Extract the source module, allowed/disallowed target, and the direction (must-import or must-not-import).

**[P5] DEPENDENCIES** — Package names with version constraints (e.g., "scipy >= 1.17", "no new dependencies", "uses existing pandas"). Extract package name and version constraint or "no new deps" assertion.

**[P6] ARCHITECTURE** — Claims about field counts ("N fields"), base classes ("extends BaseModel"), function existence ("adds `function_name()`"), method signatures, or class inheritance.

**[P7] LIBRARY APIs** — References to external library functions or behavior (e.g., "`scipy.optimize.brentq`", "`yfinance.Ticker.options`", "`numpy.polynomial.polynomial.Polynomial.fit`"). Tag these for `--full` mode only.

Collect all claims into a structured list with: category, claim text, source line/section, and verification target.

Report:
```
Claims extracted: {N} ([P1]: {n1}, [P2]: {n2}, [P3]: {n3}, [P4]: {n4}, [P5]: {n5}, [P6]: {n6}, [P7]: {n7})
```

## Step 2b: PRD Claim Verification (PRD-audit mode only)

Verify each extracted claim using the appropriate tool:

**[P1] FILE PATHS** — Use `Glob` to check if each path exists under `src/options_arena/` (or the stated location). Also check `data/migrations/`, `tests/`, etc. as appropriate.
- EXISTS → FOUND
- Not exists → NOT_FOUND

**[P2] MODEL FIELDS** — Use `Grep` to search for the field name in the model's expected source file. If the model file is known (from P1 or from project knowledge), read it and verify the field exists with the expected type.
- Field exists with matching type → FOUND
- Field exists with different type → MISMATCH (report actual type)
- Field not found → NOT_FOUND

**[P3] ENUM VARIANTS** — Use `Grep` to search for the variant name in the expected enum class file (typically `models/enums.py`).
- Variant exists → FOUND
- Variant not found → NOT_FOUND

**[P4] IMPORT BOUNDARIES** — Use `Grep` to scan actual imports in the target module.
- For "must not import X": grep for `import X` or `from X` in the source module. No matches → COMPLIANT. Matches → VIOLATION.
- For "imports X only": grep for all imports in the source file, verify they only reference allowed targets. All compliant → COMPLIANT. Extra imports → VIOLATION.

**[P5] DEPENDENCIES** — Use `Read` on `pyproject.toml`. Find the package in `[project.dependencies]` or `[project.optional-dependencies]`. Compare version constraints.
- Package found with compatible version → MATCH
- Package found with incompatible version → MISMATCH
- Package not found (when "no new deps" claimed) → MATCH
- Package not found (when expected to exist) → NOT_FOUND

**[P6] ARCHITECTURE** — Use `Read` and/or `Grep` on the relevant source file(s). Verify field counts, base class inheritance, function definitions, etc.
- Claim matches reality → MATCH
- Claim contradicts reality → MISMATCH (report actual)
- Target file doesn't exist → NOT_FOUND

**[P7] LIBRARY APIs** (only with `--full`) — Use Context7 MCP: first `resolve-library-id` for the library, then `query-docs` to verify the API claim. If Context7 MCP is unavailable, report SKIPPED.
- API exists as claimed → VERIFIED
- API differs from claim → MISMATCH (report actual)
- Cannot verify → SKIPPED

Without `--full`, report all P7 claims as SKIPPED with note "use --full for library API verification".

### Status-Aware Result Interpretation

NOT_FOUND results are interpreted based on PRD frontmatter `status`:

| PRD Status | NOT_FOUND for new files/fields | Severity |
|------------|-------------------------------|----------|
| `planned` or `researched` | Expected — these don't exist yet | **INFO** |
| `in-progress` | May or may not exist yet | **WARN** |
| `completed` | Should exist — something is wrong | **FAIL** |

MISMATCH and VIOLATION are always **FAIL** regardless of status (the PRD contradicts existing code).
FOUND, MATCH, COMPLIANT, VERIFIED are always **PASS**.

## Step 3: Full Mode (only with --full, code-audit mode only)

*Skip this step in PRD-audit mode — `--full` in PRD mode enables P7 library API checks in Step 2b.*

If `--full` was specified, run two additional steps:

**[4] TYPES (mypy)**
```bash
uv run mypy {target} --strict 2>&1; echo "EXIT:$?"
```
Result: PASS if exit code 0, FAIL if type errors found.

**[5] AUDIT AGENTS** — Determine which agents to launch based on which modules are in scope.
Use file paths to match:

| Path contains | Agent | Description |
|---------------|-------|-------------|
| `pricing/`, `scoring/`, `indicators/` | `oa-python-reviewer` | Financial precision review |
| `models/` | `code-reviewer` | Model conventions review |
| `data/` | `db-auditor` | Database layer audit |
| `api/`, `services/` | `security-auditor` | Security audit |
| *(any file)* | `architect-reviewer` | Architecture review |

Launch all matched agents in a SINGLE message for parallelism. Each agent gets the list
of in-scope files relevant to its domain. Collect their findings.

## Step 4: Report

### Code-audit report format

Output this exact format:

```
STRUCTURAL CHECK
================
Scope: {description}
Files: {N} files checked

[1] BOUNDARIES (tach)      {PASS | FAIL | WARN} — {details if non-pass}
[2] STRUCTURE (ast-grep)   {PASS | FAIL | WARN} — {details if non-pass}
[3] LINT (ruff)            {PASS | FAIL | WARN} — {details if non-pass}
[4] TYPES (mypy)           {PASS | FAIL | WARN} — {details if non-pass}    ← only with --full

VERDICT: {PASS | FAIL} ({N} checks passed, {M} failed)
```

If `--full` was used and audit agents returned findings, append them after the verdict:

```
AUDIT FINDINGS
==============
[agent-name] {summary of findings}
```

Verdict rules:
- Any FAIL → overall FAIL
- WARN-only → overall PASS (warnings noted)
- All PASS → overall PASS

### PRD-audit report format

Output this exact format for each PRD:

```
PRD AUDIT
=========
PRD: {name} (status: {status})
Claims extracted: {N}

[P1] FILE PATHS          {found} found, {missing} missing             {PASS|FAIL|INFO|WARN}
[P2] MODEL FIELDS        {found} found, {mismatch} mismatch, {pending} pending  {PASS|FAIL|INFO|WARN}
[P3] ENUM VARIANTS       {found} found, {pending} pending             {PASS|FAIL|INFO|WARN}
[P4] IMPORT BOUNDARIES   {compliant} compliant, {violations} violations  {PASS|FAIL}
[P5] DEPENDENCIES        {match} match, {mismatch} mismatch           {PASS|FAIL}
[P6] ARCHITECTURE        {match} match, {mismatch} mismatch           {PASS|FAIL|INFO|WARN}
[P7] LIBRARY APIs        {verified}/{total} verified                   {PASS|FAIL|SKIPPED}

VERDICT: {PASS | FAIL | INFO} ({summary})
```

For FAIL or WARN lines, append ` — {details}` with specifics (which files missing, which fields mismatched, etc.).

When auditing multiple PRDs, output one report block per PRD, then a combined summary:

```
COMBINED SUMMARY
================
{N} PRDs audited: {pass_count} PASS, {fail_count} FAIL, {info_count} INFO
```

PRD verdict rules:
- Any MISMATCH or VIOLATION → **FAIL** (PRD contradicts existing code)
- NOT_FOUND in `completed` PRD → **FAIL**
- NOT_FOUND in `in-progress` PRD (only) → **WARN** (upgraded to INFO in verdict if no FAILs)
- NOT_FOUND in `planned`/`researched` PRD (only, no FAILs) → **INFO** (expected, not yet built)
- All FOUND/MATCH/COMPLIANT → **PASS**

</instructions>

<constraints>
1. NEVER modify code — this is a read-only verification command
2. NEVER write stamp files — no `.context7-stamp` mechanism
3. Report tool-not-found as WARN, not FAIL (tach/ast-grep may not be installed)
4. Run deterministic checks before any agent-based analysis
5. Only launch audit agents when `--full` is explicitly specified
6. Keep output concise — full tool output only on FAIL, summary on PASS
7. In PRD-audit mode, skip tach/ast-grep/ruff/mypy — these check code, not PRDs
8. PRD claims about not-yet-implemented features are INFO (not FAIL) for planned/researched PRDs
</constraints>