# Context7 Verification Guide

Two separate things share the "Context7" name:

1. **`/context7` command** — Fast structural verification (tach + ast-grep + ruff + optional mypy/agents)
2. **Context7 MCP** — External library API verification via `resolve-library-id` + `query-docs`

This guide covers both.

## /context7 Command

Fast deterministic checks on changed or specified files. No code modification.

### Usage

| Command | What it checks |
|---------|---------------|
| `/context7` | Changed files only (git diff) |
| `/context7 all` | Entire `src/` |
| `/context7 <path>` | Specific file or directory |
| `/context7 --full` | Above + mypy + relevant audit agents |

### Checks Run

1. **tach check** — Module boundary enforcement (always whole-project)
2. **ast-grep scan** — 4 structural rules (no-direct-pricing-import, no-optional-syntax, no-print-in-library, no-raw-dict-return)
3. **ruff check** — Lint on target scope
4. **mypy --strict** — Type checking (only with `--full`)
5. **Audit agents** — Domain-specific review (only with `--full`)

## Context7 MCP — External Library Verification

Before writing code that maps external library output to typed models, use Context7 MCP
(`resolve-library-id` then `query-docs`) to verify field names, return types, and signatures.

### When to Verify

- Writing a new service method that parses library output (yfinance, pandas, scipy, httpx)
- Adding/modifying Pydantic models whose fields map to external library data
- Using library functions with parameters not yet used in this project
- Setting up Typer commands, Rich handlers, or pydantic-settings config

### What to Verify

- **Field/column names**: exact spelling, casing (e.g., yfinance uses camelCase in `.info`)
- **Return types**: what the function actually returns (DataFrame, dict, Series, etc.)
- **Parameter signatures**: required vs optional args, defaults, valid options
- **Data shapes**: which fields can be `None`, which are always present

### Known Wrong Assumptions (Caught by Prior Verification)

- "yfinance option chains include Greeks" — **FALSE**. Only `impliedVolatility`. All Greeks from `pricing/dispatch.py`.
- "Typer supports async command functions" — **UNRELIABLE**. Always sync def + `asyncio.run()`.
- "RichHandler handles all log messages safely" — **FALSE**. `markup=False` required.
- "pydantic-settings nested delimiter just works" — **PARTIALLY**. May need `env_nested_max_split`.

Do NOT commit code that maps external library output to typed models without Context7
verification. If Context7 MCP is unavailable, note the assumption as **unverified** in a
code comment.

## PRD Audit Mode

`/context7 prd` audits technical claims in PRD files against the codebase. Catches wrong
file paths, misnamed model fields, stale dependency versions, and boundary violations before
PRD-to-epic conversion.

### Usage

| Command | What it does |
|---------|-------------|
| `/context7 prd` | Audit all PRDs in `.claude/prds/` |
| `/context7 prd <name>` | Audit a specific PRD (e.g., `volatility-intelligence`) |
| `/context7 prd --full` | Also verify library API claims via Context7 MCP |

### Claim Categories

7 check categories (P1-P7): file paths, model fields, enum variants, import boundaries,
dependencies, architecture, and library APIs. See the command file for the full taxonomy.

### Status Awareness

NOT_FOUND results are interpreted based on PRD `status` frontmatter:
- `planned`/`researched`: NOT_FOUND = **INFO** (features not yet built)
- `in-progress`: NOT_FOUND = **WARN**
- `completed`: NOT_FOUND = **FAIL**

MISMATCH and VIOLATION are always FAIL regardless of status.
