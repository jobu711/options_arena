# Context7 MCP — External Library Verification

Before writing code that maps external library output to typed models, use Context7 MCP
(`resolve-library-id` then `query-docs`) to verify field names, return types, and signatures.

## When to Verify

- Writing a new service method that parses library output (yfinance, pandas, scipy, httpx)
- Adding/modifying Pydantic models whose fields map to external library data
- Using library functions with parameters not yet used in this project
- Setting up Typer commands, Rich handlers, or pydantic-settings config

## What to Verify

- **Field/column names**: exact spelling, casing (e.g., yfinance uses camelCase in `.info`)
- **Return types**: what the function actually returns (DataFrame, dict, Series, etc.)
- **Parameter signatures**: required vs optional args, defaults, valid options
- **Data shapes**: which fields can be `None`, which are always present

## Known Wrong Assumptions (Caught by Prior Verification)

- "yfinance option chains include Greeks" — **FALSE**. Only `impliedVolatility`. All Greeks from `pricing/dispatch.py`.
- "Typer supports async command functions" — **UNRELIABLE**. Always sync def + `asyncio.run()`.
- "RichHandler handles all log messages safely" — **FALSE**. `markup=False` required.
- "pydantic-settings nested delimiter just works" — **PARTIALLY**. May need `env_nested_max_split`.

Do NOT commit code that maps external library output to typed models without Context7
verification. If Context7 MCP is unavailable, note the assumption as **unverified** in a
code comment.

## PRD Audit Mode

`/context7 prd` audits technical claims in PRD files against the codebase. Run after
writing or editing a PRD — catches stale paths, misnamed fields, wrong dependency
versions, and boundary violations before epic decomposition.

- `/context7 prd` — audit all PRDs in `.claude/prds/`
- `/context7 prd <name>` — audit a specific PRD
- `/context7 prd <name> --full` — also verify library API claims (P7) via Context7 MCP

7 claim categories (P1-P7): file paths, model fields, enum variants, import boundaries,
dependencies, architecture, library APIs. NOT_FOUND severity depends on PRD `status`
frontmatter (`planned` = INFO, `in-progress` = WARN, `completed` = FAIL).
