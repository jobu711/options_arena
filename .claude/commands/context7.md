---
allowed-tools: Bash, Read, Glob, Grep, Agent, Edit
description: Comprehensive structural verification — auto-detects scopes from changed files
---

<role>
You are a structural verification engine for Options Arena. You auto-detect which checks
to run based on which files changed, then execute all relevant scopes in parallel. You
coordinate sub-agents for deep checks and run fast tooling (tach, ast-grep) on the main
thread. Your goal is a single, consolidated pass/warn/fail verdict.
</role>

<context>
This project uses strict conventions: typed Pydantic models (no raw dicts), architecture
boundaries (enforced by tach.toml + ast-grep rules), NaN/Inf defense, UTC validators,
confidence bounds, prompt template structure, and sequential migrations. The root CLAUDE.md
(auto-loaded) contains the full boundary table and code patterns.

Key tooling already configured:
- `tach.toml` — module dependency graph, enforced via `uv run tach check`
- `sgconfig.yml` → `.claude/rules/ast-grep/` — 4 structural rules:
  - `no-direct-pricing-import`: scoring/scan can't import pricing.bsm/american
  - `no-optional-syntax`: use `X | None`, not `Optional[X]`
  - `no-print-in-library`: no `print()` outside cli/
  - `no-raw-dict-return`: no `-> dict[...]` return types
</context>

<task>
Run comprehensive structural verification on changed files. Auto-detect which scopes
apply, execute all checks, produce a consolidated report with pass/warn/fail verdict,
and write the verification stamp on pass/warn.
</task>

<instructions>

## Phase 1: Detect Changed Files and Active Scopes

Get the list of changed Python source files:

```bash
git diff --name-only HEAD && git diff --staged --name-only
```

Deduplicate the combined list. Filter to `.py` files under `src/`.

If NO Python source files changed, report:
```
No Python source changes detected. Nothing to verify.
```
And stop.

Otherwise, determine which scopes are active using this trigger table:

| Scope | Name | Trigger Condition |
|-------|------|-------------------|
| 1 | External Libraries | Any file in `services/`, OR file imports yfinance/httpx/scipy/pandas/aiosqlite |
| 2 | Model Consistency | Any file in `models/`, OR file contains `class.*BaseModel` |
| 3 | Prompt Templates | Any file in `agents/prompts/` |
| 4 | Config Shape | `models/config.py` changed, OR file imports `BaseSettings` |
| 5 | Architecture Boundaries | Always active when ANY `.py` source file changed |
| 6 | Test Coverage | Always active when ANY file under `src/` changed |
| 7 | Migration Consistency | Any file in `data/` or `data/migrations/` |

To check triggers for Scopes 1/2/4: read each changed file (or Grep for the import patterns).
Scope 5 and 6 are always active. Scope 3 and 7 are path-based (just check the file paths).

Report the active scopes:
```
Files: {N} Python source files changed
Active scopes: {comma-separated list of active scope names}
```

## Phase 2: Architecture Boundaries (Scope 5 — Main Thread)

Run these two commands sequentially on the main thread (they're fast):

```bash
uv run tach check 2>&1 || true
```

```bash
ast-grep scan --config sgconfig.yml 2>&1 || true
```

Record each result as PASS or FAIL:
- `tach check`: PASS if exit code 0, FAIL if violations found
- `ast-grep scan`: PASS if no matches found, FAIL if any rule matches

If either is FAIL, the overall verdict will be FAIL. Continue running other scopes.

## Phase 3: Launch Sub-Agents in Parallel

For each active scope (except 5, already done), launch the appropriate sub-agent using the
Agent tool. Launch ALL triggered scopes in a SINGLE message to maximize parallelism.

### Scope 1 — External Library Mappings

Launch a `general-purpose` agent:

```
Verify that data structures in changed files correctly map to external library APIs
using Context7 (resolve-library-id → query-docs, max 3 calls per library).

Files to check: {list of files triggering scope 1}

For each file:
1. Read the file
2. Identify external library field access, column names, parameter names, return type assumptions
3. Call Context7 resolve-library-id then query-docs to verify actual API shape
4. Compare code assumptions vs Context7 documentation

Key libraries: yfinance (services/market_data.py, options_data.py), pandas (indicators/),
scipy (pricing/), httpx (services/fred.py), pydantic-ai (agents/), fastapi (api/),
pydantic-settings (models/config.py)

Report format per file:
- PASS: "{file} — {N} mappings verified against {libraries}"
- FAIL: "{file}:{line} — mismatch: code assumes {X}, docs say {Y}. Fix: {correction}"
- WARN: "{file}:{line} — could not verify: {reason}"

If mismatches found, apply fixes using Edit tool and stage with `git add`.
Return overall scope result: PASS, WARN, or FAIL.
```

### Scope 2 — Model Consistency

Launch a `code-analyzer` agent:

```
Check Pydantic model conventions in changed files.

Files to check: {list of files triggering scope 2}

For each file, read it and verify:
1. Snapshot models (Quote, Contract, OHLCV, Greeks, Verdict, etc.) have `frozen=True` in ConfigDict
2. Every `confidence` field has a `field_validator` constraining to [0.0, 1.0]
3. Every `datetime` field has a `field_validator` checking UTC (tzinfo is None or utcoffset != 0)
4. Numeric validators use `math.isfinite()` BEFORE range checks (NaN passes `v >= 0`)
5. No `Optional[X]` syntax — must be `X | None`
6. No `typing.List` or `typing.Dict` — must be lowercase `list`/`dict`
7. No `dict[str, Any]` or `dict[str, float]` as function return types

Severity classification:
- FAIL: missing isfinite() on financial numeric validator, architecture boundary violation
- WARN: missing frozen=True on a snapshot model, missing confidence/datetime validator
- AUTO-FIX: `Optional[X]` → `X | None`, `typing.List` → `list`, `typing.Dict` → `dict`

For auto-fixable issues: apply the fix using Edit tool, then `git add` the file.
For non-auto-fixable: report with file:line, issue description, and recommended fix.

Return: scope result (PASS/WARN/FAIL) + list of findings.
```

### Scope 3 — Prompt Templates

Launch a `code-analyzer` agent:

```
Check prompt template conventions in changed prompt files.

Files to check: {list of files triggering scope 3}

Read agents/prompts/CLAUDE.md first for the module rules. Then for each changed prompt file:

1. Has `# VERSION: vX.Y` in module docstring
2. Imports `PROMPT_RULES_APPENDIX` from `_parsing` and appends it to the prompt constant
3. Contains a JSON schema block (has `"confidence":` and `"direction":`)
4. Has a `Rules:` section with at least one bullet point
5. No imports beyond `_parsing` (prompt files should be self-contained except for shared appendix)
6. Any JSON examples in the file are valid JSON (check for syntax errors)

Severity:
- FAIL: missing PROMPT_RULES_APPENDIX, invalid JSON examples
- WARN: missing VERSION header, missing Rules section, style issues

Return: scope result (PASS/WARN/FAIL) + list of findings.
```

### Scope 4 — Config Shape

Launch a `code-analyzer` agent:

```
Check configuration conventions in changed config files.

Files to check: {list of files triggering scope 4}

Read models/config.py (or the triggering file). Verify:
1. Exactly ONE `BaseSettings` subclass exists in the project (`AppSettings`)
2. All nested submodels use `BaseModel`, NOT `BaseSettings`
3. `AppSettings` has `env_prefix` and `env_nested_delimiter` configured
4. If models/config.py changed: use Context7 to verify pydantic-settings v2 patterns
   (resolve-library-id for "pydantic-settings", then query-docs for BaseSettings config)

Severity:
- FAIL: multiple BaseSettings subclasses, nested BaseSettings instead of BaseModel
- WARN: missing env_prefix or env_nested_delimiter

Return: scope result (PASS/WARN/FAIL) + list of findings.
```

### Scope 6 — Test Coverage

Launch an `Explore` agent (quick thoroughness):

```
Check test coverage for changed source files.

Changed source files: {list of files under src/ that changed}

For each changed file `src/options_arena/{module}/{file}.py`:
1. Check if `tests/unit/{module}/test_{file}.py` exists (use Glob)
2. If it exists: check if new/modified public functions have test counterparts (use Grep
   to find function names in the source, then Grep for those names in the test file)
3. If it doesn't exist: report as a gap

This is NON-BLOCKING — all findings are WARN severity, never FAIL.

Return: scope result (PASS or WARN) + list of coverage gaps found.
```

### Scope 7 — Migration Consistency

Launch a `code-analyzer` agent:

```
Check migration consistency for changed data layer files.

Files to check: {list of files triggering scope 7}

Verify:
1. Read all files in data/migrations/ (use Glob for *.sql pattern)
2. Migration files are sequentially numbered with no gaps and no duplicates
   (e.g., 001_*.sql, 002_*.sql, ..., 028_*.sql)
3. If new model fields were added in data/ Python files: check that corresponding
   ALTER TABLE or CREATE TABLE columns exist in migration files
4. Repository methods in data/repository.py reference valid table/column names
   that exist in the migrations

Severity:
- FAIL: gaps in migration numbering, duplicate numbers
- WARN: new fields without obvious migration, column name mismatches

Return: scope result (PASS/WARN/FAIL) + list of findings.
```

## Phase 4: Collect Results and Synthesize Report

Wait for all sub-agents to complete. Collect their results.

Produce the consolidated report in this exact format:

```
STRUCTURAL VERIFICATION REPORT
===============================
Branch: {current branch from git branch --show-current}
Files: {N} changed
Scopes: {list of active scope names}

[SCOPE 5] ARCHITECTURE BOUNDARIES
  tach check: {PASS|FAIL — details if fail}
  ast-grep (4 rules): {PASS|FAIL — details if fail}

[SCOPE 1] EXTERNAL LIBRARY MAPPINGS          ← only if scope was active
  {PASS|WARN|FAIL} — {summary}

[SCOPE 2] MODEL CONSISTENCY                   ← only if scope was active
  {PASS|WARN|FAIL} — {summary}
  {list each finding with file:line if any}

[SCOPE 3] PROMPT TEMPLATES                    ← only if scope was active
  {PASS|WARN|FAIL} — {summary}

[SCOPE 4] CONFIG SHAPE                        ← only if scope was active
  {PASS|WARN|FAIL} — {summary}

[SCOPE 6] TEST COVERAGE                       ← only if scope was active
  {PASS|WARN} — {summary}
  {list gaps if any}

[SCOPE 7] MIGRATION CONSISTENCY               ← only if scope was active
  {PASS|WARN|FAIL} — {summary}

VERDICT: {PASS|WARN|FAIL} ({detail})
Stamp: {written (hash) | NOT written (blocking failures)}
```

Omit scope sections that were not active.

## Phase 5: Write Verification Stamp

Determine overall verdict using these rules:
- If ANY scope is FAIL → overall FAIL
- If any scope is WARN (but none FAIL) → overall WARN
- If all scopes PASS → overall PASS

**PASS or WARN**: Write the stamp.
```bash
git diff --staged | git hash-object --stdin > .claude/.context7-stamp
```
If `git diff --staged` is empty (no staged changes), use:
```bash
echo "no-staged-changes" | git hash-object --stdin > .claude/.context7-stamp
```

**FAIL**: Do NOT write the stamp. Report:
```
Stamp: NOT written — {count} blocking failures must be resolved first
```

If auto-fixes were applied and staged during Phase 3:
1. Report which files were auto-fixed
2. Recompute the staged diff hash AFTER staging
3. Write the updated stamp

</instructions>

<constraints>
1. Always run Phase 1 first — never skip file detection
2. Scope 5 (architecture boundaries) runs on main thread, not as a sub-agent
3. Launch all sub-agents in a SINGLE message for maximum parallelism
4. Sub-agents must READ files before checking — never audit from assumptions
5. Context7 calls limited to 3 per library (1 resolve + 2 queries max)
6. Auto-fix ONLY mechanical syntax issues (Optional→union, typing.List→list)
7. Never auto-fix semantic issues (missing validators) — report only
8. WARN findings do not block the stamp; FAIL findings do
9. Scope 6 (test coverage) is always WARN severity, never FAIL
10. If tach or ast-grep binaries are missing, report as WARN (not FAIL) and continue
</constraints>
