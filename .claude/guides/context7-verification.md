# Context7 Verification — Structural Verification Guide

The `/context7` command runs comprehensive structural verification on changed files. It
auto-detects which checks to run based on what changed, covering 7 scopes:

| Scope | What it checks | Trigger |
|-------|---------------|---------|
| External Libraries | API field names, return types, signatures via Context7 MCP | Files in `services/` or importing yfinance/httpx/scipy |
| Model Consistency | frozen, validators, NaN defense, no raw dicts | Files in `models/` or defining BaseModel subclasses |
| Prompt Templates | VERSION header, PROMPT_RULES_APPENDIX, JSON schema | Files in `agents/prompts/` |
| Config Shape | Single BaseSettings, nested BaseModel, env config | `models/config.py` or BaseSettings imports |
| Architecture Boundaries | tach dependency graph + ast-grep structural rules | Any changed `.py` source file |
| Test Coverage | Test file existence + function coverage | Any changed file under `src/` |
| Migration Consistency | Sequential numbering, column alignment | Files in `data/` or `data/migrations/` |

## External Library Verification (Scope 1)

Before writing or modifying code that depends on the shape of data returned by an external
library (yfinance, pandas, scipy, httpx, etc.), you MUST use Context7 (`resolve-library-id`
then `query-docs`) to verify the actual field names, column names, return types, and method
signatures. Do NOT rely on training data assumptions — libraries change between versions.

### When to verify

- **Writing a new service method** that parses library output (e.g., yfinance `option_chain()`,
  `Ticker.info`, `Ticker.get_dividends()`).
- **Adding or modifying a Pydantic model** whose fields map to external library data shapes
  (e.g., `OptionContract` fields matching yfinance chain columns).
- **Using `pd.read_html()`**, `pd.read_csv()`, or any parser where column names come from
  an external source (e.g., Wikipedia table headers).
- **Calling a library function** with parameters you haven't used before in this project.
- **Setting up Typer commands, Rich handlers, or pydantic-settings config** — verify parameter
  names, enum support, and async compatibility.

### What to verify

- **Field/column names**: exact spelling, casing (e.g., yfinance uses camelCase in `.info`).
- **Return types**: what the function actually returns (DataFrame, dict, Series, namedtuple).
- **Parameter signatures**: required vs optional args, default values, valid options.
- **Data shapes**: which fields can be `None`, which are always present, value ranges.

### How to verify

```
1. resolve-library-id  — get the Context7 library ID
2. query-docs          — ask the specific question about the data shape
3. Document findings   — update the relevant PRD requirement or system-patterns.md
                         with "(Context7-verified)" annotation
```

### Assumptions that were wrong before Context7 verification

- "yfinance option chains include Greeks (delta, gamma, theta, vega)" — **FALSE**.
  Chains only include `impliedVolatility`. All Greeks computed locally via `pricing/dispatch.py`.
- "Wikipedia S&P 500 table can be fetched with `pd.read_html(url)[0]`" — **FRAGILE**.
  Target with `attrs={"id": "constituents"}`.
- "Typer supports async command functions" — **UNRELIABLE**.
  Always use sync def + `asyncio.run()`.
- "RichHandler handles all log messages safely" — **FALSE**.
  `markup=False` required to prevent `[ticker]` bracket crashes.
- "pydantic-settings nested delimiter just works" — **PARTIALLY**.
  `env_nested_delimiter="__"` can mismatch on fields with underscores; may need
  `env_nested_max_split` for complex nesting.

Do NOT commit code that maps external library output to typed models without Context7
verification in the current conversation. If Context7 is unavailable, note the assumption
as **unverified** in a code comment and in the relevant PRD section.

## Three-State Verdict

| State | Meaning | Stamp written? |
|-------|---------|----------------|
| PASS | All checks passed | Yes |
| WARN | Non-blocking issues (missing tests, style) | Yes |
| FAIL | Blocking issues (boundary violations, API mismatches) | No |

**FAIL triggers**: architecture boundary violations (tach/ast-grep), external library
mismatches, migration gaps/duplicates, config shape violations.

**WARN triggers**: missing test files, missing validators (reported only), prompt style issues.

The stamp is written to `.claude/.context7-stamp` and checked by the pre-commit hook.
