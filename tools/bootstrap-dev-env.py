"""Bootstrap a generic Python dev environment from Options Arena's Claude Code setup.

Creates a full .claude/ directory structure at DEV with:
- All generic PM/workflow commands (~46 files)
- Generic guides, rules, ast-grep rules
- Templated CLAUDE.md, pyproject.toml, .gitignore, .mcp.json, etc.
- Domain-stripped agent definitions

Usage:
    python tools/bootstrap-dev-env.py
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

SRC = Path("C:/Users/nicho/Desktop/Options_Arena")
DST = Path("C:/Users/nicho/Desktop/DEV")

# ---------------------------------------------------------------------------
# 1. Verbatim copies — relative to project root
# ---------------------------------------------------------------------------

VERBATIM_COPIES: list[str] = [
    # Rules
    ".claude/rules/standard-patterns.md",
    ".claude/rules/ast-grep/no-print-in-library.yml",
    ".claude/rules/ast-grep/no-optional-syntax.yml",
    ".claude/rules/ast-grep/no-raw-dict-return.yml",
    # Guides (10 generic ones — context7-verification and dependency-reference are templated)
    ".claude/guides/agent-coordination.md",
    ".claude/guides/branch-operations.md",
    ".claude/guides/datetime.md",
    ".claude/guides/frontmatter-operations.md",
    ".claude/guides/github-operations.md",
    ".claude/guides/path-standards.md",
    ".claude/guides/strip-frontmatter.md",
    ".claude/guides/test-execution.md",
    ".claude/guides/use-ast-grep.md",
    ".claude/guides/worktree-operations.md",
    # Agents (4 fully generic)
    ".claude/agents/code-analyzer.md",
    ".claude/agents/file-analyzer.md",
    ".claude/agents/test-runner.md",
    ".claude/agents/parallel-worker.md",
    # Commands — root level (3 verbatim; bug, context7, prompt are templated)
    ".claude/commands/analyze.md",
    ".claude/commands/code-rabbit.md",
    ".claude/commands/re-init.md",
    # Commands — context/
    ".claude/commands/context/create.md",
    ".claude/commands/context/prime.md",
    ".claude/commands/context/update.md",
    # Commands — testing/
    ".claude/commands/testing/prime.md",
    ".claude/commands/testing/run.md",
    # Commands — pm/ (all 41)
    ".claude/commands/pm/blocked.md",
    ".claude/commands/pm/clean.md",
    ".claude/commands/pm/epic-checkpoint.md",
    ".claude/commands/pm/epic-close.md",
    ".claude/commands/pm/epic-decompose.md",
    ".claude/commands/pm/epic-edit.md",
    ".claude/commands/pm/epic-list.md",
    ".claude/commands/pm/epic-merge.md",
    ".claude/commands/pm/epic-oneshot.md",
    ".claude/commands/pm/epic-refresh.md",
    ".claude/commands/pm/epic-resume.md",
    ".claude/commands/pm/epic-show.md",
    ".claude/commands/pm/epic-start.md",
    ".claude/commands/pm/epic-start-worktree.md",
    ".claude/commands/pm/epic-status.md",
    ".claude/commands/pm/epic-sync.md",
    ".claude/commands/pm/help.md",
    ".claude/commands/pm/import.md",
    ".claude/commands/pm/in-progress.md",
    ".claude/commands/pm/init.md",
    ".claude/commands/pm/issue-analyze.md",
    ".claude/commands/pm/issue-close.md",
    ".claude/commands/pm/issue-edit.md",
    ".claude/commands/pm/issue-reopen.md",
    ".claude/commands/pm/issue-show.md",
    ".claude/commands/pm/issue-start.md",
    ".claude/commands/pm/issue-status.md",
    ".claude/commands/pm/issue-sync.md",
    ".claude/commands/pm/next.md",
    ".claude/commands/pm/prd-edit.md",
    ".claude/commands/pm/prd-list.md",
    ".claude/commands/pm/prd-new.md",
    ".claude/commands/pm/prd-parse.md",
    ".claude/commands/pm/prd-research.md",
    ".claude/commands/pm/prd-status.md",
    ".claude/commands/pm/search.md",
    ".claude/commands/pm/standup.md",
    ".claude/commands/pm/status.md",
    ".claude/commands/pm/sync.md",
    ".claude/commands/pm/test-reference-update.md",
    ".claude/commands/pm/validate.md",
    # Config
    "sgconfig.yml",
]


# ---------------------------------------------------------------------------
# 2. Templated file generators
# ---------------------------------------------------------------------------


def gen_claude_md() -> str:
    return textwrap.dedent("""\
    # CLAUDE.md — My Project

    @.claude/context/tech-context.md
    @.claude/context/progress.md
    @.claude/context/system-patterns.md

    ## What This Project Does

    TODO: Describe your project in 2-3 sentences.

    ## Tech Stack

    - **Python 3.13+** — use modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
    - **Package manager**: `uv` — always `uv add <pkg>`, never `pip install`
    - **Linter/Formatter**: `ruff` (target `py313`, line-length 99)
    - **Type checker**: `mypy --strict` — full annotations on every function, no exceptions
    - **Async**: `asyncio` + `httpx` — async operations use these
    - **Models**: Pydantic v2 — all structured data crosses module boundaries as typed models, never raw dicts
    - **Config**: `pydantic-settings` v2 — single `AppSettings(BaseSettings)` root, nested `BaseModel` submodels
    - **CLI**: `typer` + `rich` — subcommands, Rich tables, progress bars, colored terminal output

    ## Project Layout

    ```
    src/my_project/
        TODO: Define your module structure
    tests/
        TODO: Define your test structure
    ```

    ## Module-Level Instructions — MANDATORY

    Before creating, editing, or reviewing ANY file in a module, you MUST first read
    that module's CLAUDE.md (if it has one). These contain rules that override or extend
    the root instructions.

    ## Code Patterns — Project-Wide

    ### NO RAW DICTS — Typed Models Everywhere

    **Every function that returns structured data MUST return a Pydantic model,
    a dataclass, or a StrEnum — NEVER a `dict`, `dict[str, Any]`,
    `dict[str, float]`, or any `dict` variant.**

    ```python
    # WRONG — raw dict
    def get_result(item: Item) -> dict[str, float]: ...

    # RIGHT — typed model
    def get_result(item: Item) -> ItemResult: ...
    ```

    ### Architecture Boundaries

    TODO: Define your module boundary table.

    | Module | Responsibility | Can Access | Cannot Access |
    |--------|---------------|------------|---------------|
    | `models/` | Data shapes + config only | Nothing | APIs, logic, I/O |
    | `services/` | External API access | `models/` | Business logic |

    ### Pydantic Model Patterns (Context7-verified)

    ```python
    from pydantic import BaseModel, ConfigDict, field_validator

    # Immutable snapshot model
    class Quote(BaseModel):
        model_config = ConfigDict(frozen=True)
        # fields...

    # UTC datetime enforcement (required on EVERY datetime field)
    @field_validator("timestamp")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("must be UTC")
        return v

    # Confidence bounds (required on EVERY confidence field)
    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v
    ```

    ### Configuration Pattern (Context7-verified: pydantic-settings v2)

    ```python
    from pydantic import BaseModel
    from pydantic_settings import BaseSettings, SettingsConfigDict

    # Nested submodels are BaseModel, NOT BaseSettings
    class FeatureConfig(BaseModel):
        enabled: bool = True

    # Single BaseSettings root — the ONLY BaseSettings subclass in the project
    class AppSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="APP_",
            env_nested_delimiter="__",
        )
        feature: FeatureConfig = FeatureConfig()
    ```

    ### CLI Patterns (Context7-verified: Typer + Rich)

    ```python
    import asyncio
    import typer

    app = typer.Typer()

    # Typer does NOT support async commands — always use asyncio.run()
    @app.command()
    def run(name: str = "default") -> None:
        asyncio.run(_run_async(name))
    ```

    **Critical gotchas**:
    - `RichHandler(markup=False)` — library logs contain brackets that crash Rich markup
    - `signal.signal()` for SIGINT, NOT `loop.add_signal_handler()` (unsupported on Windows)

    ### Error Handling

    - Custom domain exceptions in `utils/` or a dedicated exceptions module.
    - Never bare `except:` — always catch specific types.
    - `logging` module only — never `print()` in library code. `print()` is reserved for `cli/`.

    ### Naming

    - Variables: descriptive, no abbreviations (e.g., `user_count`, `daily_prices_df`).
    - Constants: `UPPERCASE` — defined once, no magic numbers.
    - DataFrames: always suffixed `_df`.

    ### Async Convention

    - Pick ONE client type per module — don't mix sync/async.
    - `asyncio.wait_for(coro, timeout=N)` on every external call. No unbounded waits.
    - `asyncio.gather(*tasks, return_exceptions=True)` for batch operations.
    - Typer commands are sync wrappers: `def cmd() -> None: asyncio.run(_cmd_async())`.

    ## Verification — Run Before Every Commit

    ```bash
    uv run ruff check . --fix && uv run ruff format .   # lint + format
    uv run pytest tests/ -n auto -q                      # all tests (parallel)
    uv run pytest tests/ -v                              # all tests (verbose, for debugging)
    uv run mypy src/ --strict                            # type checking
    ```

    Always run lint, tests, and type checking via `uv run`. A task is not done until all pass.

    ## Context7 Verification

    Before writing code that maps external library output to typed models, use Context7
    (`resolve-library-id` → `query-docs`) to verify field names, return types, and signatures.
    Full protocol: `.claude/guides/context7-verification.md`.

    ## Git Discipline

    - Atomic commits: `feat: add feature X`, not `update stuff`.
    - Branch per feature. Never commit directly to main.
    - Every commit message starts with: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, or `chore:`.

    ## What Claude Gets Wrong — Fix These

    - Don't return raw dicts — always typed models (including `dict[str, float]`, `dict[str, Any]`).
    - Don't use `Optional[X]` — use `X | None`. Don't use `typing.List`/`Dict` — use lowercase.
    - Don't use raw `str` for categorical fields — use `StrEnum`.
    - Don't add `datetime` fields without UTC validator.
    - Don't forget `field_validator` on `confidence` fields — constrain to `[0.0, 1.0]`.
    - Don't leave numeric validators without `math.isfinite()` — NaN silently passes `v >= 0`.
    - Don't use `print()` outside `cli/` — use `logging.getLogger(__name__)`.
    - Don't use `async def` on Typer commands — use sync def + `asyncio.run()`.
    - Don't use `RichHandler(markup=True)` — brackets crash Rich. Always `markup=False`.
    - Don't use `loop.add_signal_handler()` — unsupported on Windows. Use `signal.signal()`.

    ## Guides (Load When Needed)

    Reference guides in `.claude/guides/` — NOT auto-loaded, read when relevant:

    | Guide | When to load |
    |-------|-------------|
    | `context7-verification.md` | Writing code that maps external library output to models |
    | `agent-coordination.md` | Multi-agent parallel work on same epic |
    | `branch-operations.md` | Git branching for epics |
    | `worktree-operations.md` | Git worktree parallel development |
    | `path-standards.md` | Documentation/GitHub sync with path privacy |
    | `strip-frontmatter.md` | Preparing markdown for GitHub sync |
    | `frontmatter-operations.md` | Creating/editing YAML frontmatter |
    | `test-execution.md` | Running tests with test-runner agent |
    | `use-ast-grep.md` | Structural code search/refactoring |
    | `datetime.md` | Writing frontmatter timestamps (PRDs, epics, tasks) |
    | `github-operations.md` | Creating/editing GitHub issues or PRs |
    | `dependency-reference.md` | Checking dependency versions |

    ## Context Budget Policy

    Auto-loaded context has a strict budget. Every line costs attention on all tasks.

    | Category | Current | Max |
    |----------|---------|-----|
    | CLAUDE.md | ~180 lines | 350 lines |
    | @-referenced context files | ~30 lines | 300 lines |
    | .claude/rules/ files | ~33 lines | 400 lines |
    | **Grand total** | **~243** | **1,050** |

    Rules:
    - `progress.md`: Current state only. Move completed work to `progress-archive.md`.
    - `system-patterns.md`: Unique patterns only. No duplication with CLAUDE.md.
    - Rules: Only universally-needed rules in `.claude/rules/`. Workflow-specific → `.claude/guides/`.
    - When adding content to any auto-loaded file, remove or move equal or greater content.
    """)


def gen_pyproject_toml() -> str:
    return textwrap.dedent("""\
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

    [project]
    name = "my-project"
    version = "0.1.0"
    description = "TODO: Project description"
    requires-python = ">=3.13"
    dependencies = [
        "httpx>=0.28",
        "pydantic>=2.12",
        "pydantic-settings>=2.13",
        "rich>=14.3",
        "typer>=0.24",
    ]

    [project.scripts]
    my-project = "my_project.cli:app"

    [tool.hatch.build.targets.wheel]
    packages = ["src/my_project"]

    [dependency-groups]
    dev = [
        "mypy>=1.19",
        "pytest>=9.0",
        "pytest-asyncio>=1.3",
        "pytest-cov>=7.0",
        "pytest-timeout>=2.4.0",
        "pytest-xdist>=3.8.0",
        "ruff>=0.15",
    ]

    # --- Tool Configuration ---

    [tool.ruff]
    target-version = "py313"
    line-length = 99

    [tool.ruff.lint]
    select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]

    [tool.mypy]
    strict = true
    warn_return_any = true
    warn_unused_configs = true

    [tool.pytest.ini_options]
    asyncio_mode = "auto"
    testpaths = ["tests"]
    addopts = "--durations=20 --timeout=60"
    markers = [
        "integration: marks tests as integration tests (may require external services)",
        "slow: marks tests expected to take >1s (deselect with -m 'not slow')",
        "smoke: marks critical-path tests for fast pre-commit sanity checks",
    ]
    """)


def gen_gitignore() -> str:
    return textwrap.dedent("""\
    # Python
    __pycache__/
    *.py[cod]
    *$py.class
    *.egg-info/
    dist/
    build/
    .eggs/

    # Virtual environments
    .venv/
    venv/

    # IDE
    .vscode/
    .idea/
    *.swp
    *.swo
    *.tmp.*

    # OS artifacts
    nul
    Thumbs.db
    .DS_Store

    # Local config (not shared)
    .claude/settings.local.json
    .mcp.json

    # Environment secrets
    .env
    .env.*

    # Coverage
    htmlcov/
    .coverage
    .coverage.*

    # mypy
    .mypy_cache/

    # ruff
    .ruff_cache/

    # pytest
    .pytest_cache/

    # Architecture tools
    .tach/

    # Runtime logs
    logs/

    # Verification stamps (transient, per-session)
    .claude/.context7-stamp
    .claude/.analyze-stamp
    .claude/.hook-debug.log
    """)


def gen_coderabbit_yaml() -> str:
    return textwrap.dedent("""\
    language: en-US
    reviews:
      auto_review:
        enabled: true
        drafts: false
      path_instructions: []
    """)


def gen_mcp_json() -> str:
    dst_escaped = str(DST).replace("\\", "\\\\")
    return textwrap.dedent(f"""\
    {{
      "mcpServers": {{
        "context7": {{
          "type": "stdio",
          "command": "cmd",
          "args": ["/c", "npx", "-y", "@upstash/context7-mcp"]
        }},
        "code-index": {{
          "type": "stdio",
          "command": "uvx",
          "args": ["code-index-mcp", "--project-path", "{dst_escaped}"]
        }},
        "language-server": {{
          "type": "stdio",
          "command": "C:\\\\Users\\\\nicho\\\\go\\\\bin\\\\mcp-language-server.exe",
          "args": [
            "--workspace", "{dst_escaped}",
            "--lsp", "pyright-langserver", "--", "--stdio"
          ]
        }},
        "ast-grep": {{
          "type": "stdio",
          "command": "uvx",
          "args": ["--from", "git+https://github.com/ast-grep/ast-grep-mcp", "ast-grep-server"]
        }}
      }}
    }}
    """)


def gen_settings_json() -> str:
    return textwrap.dedent("""\
    {
      "hooks": {}
    }
    """)


def gen_tach_toml() -> str:
    return textwrap.dedent("""\
    source_roots = ["src"]
    exact = true
    forbid_circular_dependencies = true
    ignore_type_checking_imports = true
    exclude = ["tests/", ".claude/", "**/__pycache__"]

    # TODO: Define your module dependency graph
    # [[modules]]
    # path = "my_project.models"
    # depends_on = []
    """)


def gen_tech_context() -> str:
    return textwrap.dedent("""\
    # Tech Context

    ## Language & Runtime

    - **Python 3.13+** — uses modern syntax: `match`, `type X = ...`, `X | None` unions, `StrEnum`
    - **Package manager**: `uv` — always `uv add <pkg>`, never `pip install`

    ## Dependencies (Runtime Python)

    | Package | Version | Purpose |
    |---------|---------|---------|
    | pydantic | >=2.12 | Typed data models at all boundaries |
    | httpx | >=0.28 | Async HTTP client |
    | pydantic-settings | >=2.13 | Configuration management |
    | typer | >=0.24 | CLI framework with subcommands |
    | rich | >=14.3 | Terminal output formatting |

    TODO: Add your project-specific dependencies here.

    ## External Services

    TODO: Document external APIs your project depends on.

    | Service | Module | Protocol | Purpose | Fallback |
    |---------|--------|----------|---------|----------|

    ## CLI Entry Point

    - **Command**: `my-project` — entry point `my_project.cli:app` (Typer)
    - TODO: Document CLI commands
    """)


def gen_progress() -> str:
    return textwrap.dedent("""\
    # Progress

    ## Current State

    - **Version**: 0.1.0

    ## In Progress

    - None

    ## Recently Completed

    - Project bootstrapped

    ## Future Work

    - TODO: Define roadmap

    ## Blockers

    - None currently known.
    """)


def gen_system_patterns() -> str:
    return textwrap.dedent("""\
    # System Patterns

    **TODO: Document your project's unique design patterns here.**

    Keep this file for patterns NOT already covered in CLAUDE.md.
    Only patterns confirmed across multiple modules belong here.

    ## Example Patterns

    ### Repository Pattern (if using persistence)
    - TODO: Describe data access patterns

    ### Service Layer (if using external APIs)
    - TODO: Describe service patterns

    ### NaN/Inf Defense Pattern
    - **`math.isfinite()` at model boundaries**: Every numeric validator must check `isfinite()` before range checks — NaN silently passes `v >= 0`.
    - **NaN for undefined ratios**: Division-by-zero returns `float("nan")`, not `0.0`.
    """)


def gen_context7_verification() -> str:
    return textwrap.dedent("""\
    # Context7 Verification — Mandatory for External Library Interfaces

    Before writing or modifying code that depends on the shape of data returned by an external
    library, you MUST use Context7 (`resolve-library-id` then `query-docs`) to verify the actual
    field names, column names, return types, and method signatures. Do NOT rely on training data
    assumptions — libraries change between versions.

    ## When to verify

    - **Writing a new service method** that parses library output.
    - **Adding or modifying a Pydantic model** whose fields map to external library data shapes.
    - **Using `pd.read_html()`**, `pd.read_csv()`, or any parser where column names come from
      an external source.
    - **Calling a library function** with parameters you haven't used before in this project.
    - **Setting up Typer commands, Rich handlers, or pydantic-settings config** — verify parameter
      names, enum support, and async compatibility.

    ## What to verify

    - **Field/column names**: exact spelling, casing.
    - **Return types**: what the function actually returns (DataFrame, dict, Series, namedtuple).
    - **Parameter signatures**: required vs optional args, default values, valid options.
    - **Data shapes**: which fields can be `None`, which are always present, value ranges.

    ## How to verify

    ```
    1. resolve-library-id  — get the Context7 library ID
    2. query-docs          — ask the specific question about the data shape
    3. Document findings   — update relevant docs with "(Context7-verified)" annotation
    ```

    ## Known gotchas

    - "Typer supports async command functions" — **UNRELIABLE**.
      Always use sync def + `asyncio.run()`.
    - "RichHandler handles all log messages safely" — **FALSE**.
      `markup=False` required to prevent bracket crashes.
    - "pydantic-settings nested delimiter just works" — **PARTIALLY**.
      `env_nested_delimiter="__"` can mismatch on fields with underscores.

    Do NOT commit code that maps external library output to typed models without Context7
    verification in the current conversation. If Context7 is unavailable, note the assumption
    as **unverified** in a code comment.
    """)


def gen_dependency_reference() -> str:
    return textwrap.dedent("""\
    # Dependency Reference

    Full version pinning for optional and dev dependencies. Runtime Python deps
    are in `tech-context.md`. Check `pyproject.toml` for latest.

    ## Dev

    | Package | Version | Purpose |
    |---------|---------|---------|
    | ruff | >=0.15 | Linter + formatter |
    | mypy | >=1.19 | Type checker (`--strict`) |
    | pytest | >=9.0 | Test framework |
    | pytest-asyncio | >=1.3 | Async test support |
    | pytest-cov | >=7.0 | Coverage reporting |

    ## Build System

    - **Build backend**: Hatchling
    - **Source layout**: `src/my_project/` (src-based layout)

    ## Tool Configuration

    - **Ruff**: Python 3.13, line-length 99, rules E/F/I/UP/B/SIM/ANN
    - **Mypy**: `strict = true`, `warn_return_any = true`, `warn_unused_configs = true`
    - **Pytest**: async via pytest-asyncio
    """)


# ---------------------------------------------------------------------------
# 3. Domain-stripped agents
# ---------------------------------------------------------------------------


def gen_agent_architect_reviewer() -> str:
    return textwrap.dedent("""\
    ---
    name: architect-reviewer
    description: >
      Use PROACTIVELY for architectural decisions. Reviews system design,
      module boundaries, dependency direction, API design, and data model
      changes for your project's layered architecture. Invoke when changes
      span multiple modules, introduce new patterns, or modify the boundary
      table defined in CLAUDE.md.
    tools: Read, Glob, Grep
    model: opus
    color: magenta
    ---

    You are a master software architect reviewing code for architectural integrity within a strict layered architecture.

    ## Architecture Review

    Before reviewing, read the project's CLAUDE.md to understand the module boundary table.

    ### Key Principles
    - **Repository pattern**: Typed CRUD operations, never raw dicts
    - **Immutable models**: `frozen=True` on data snapshots
    - **Re-export pattern**: Import from package, not submodules
    - **DI pattern**: Top-level creates config, passes slices to modules

    ## Review Focus

    1. **Dependency direction**: All arrows point inward toward `models/`
    2. **Module cohesion**: Each module has a single clear responsibility
    3. **Interface contracts**: Modules communicate through typed Pydantic models
    4. **Abstraction level**: No leaky abstractions crossing boundaries
    5. **Pattern consistency**: New code follows established patterns
    6. **Scalability**: Changes don't create coupling that blocks future evolution

    ## Review Output Format

    ```markdown
    ## Architecture Review: [target]

    ### Boundary Violations
    - [module → module] Description of violation

    ### Pattern Inconsistencies
    - [file] Description → Recommended pattern

    ### Coupling Concerns
    - [Description] → Impact on future evolution

    ### Positive Design Decisions
    - [What's architecturally sound]
    ```
    """)


def gen_agent_code_reviewer() -> str:
    return textwrap.dedent("""\
    ---
    name: code-reviewer
    description: >
      Use PROACTIVELY for code quality assurance. Reviews code for security
      vulnerabilities, performance issues, OWASP compliance, clean code
      principles, and project-specific patterns (no raw dicts, typed
      models, architecture boundaries, NaN defense). Invoke for PR reviews,
      pre-commit quality gates, or targeted code audits.
    tools: Read, Glob, Grep, Bash
    model: opus
    color: red
    ---

    You are an elite code reviewer specializing in Python 3.13+ codebases with strict typing, Pydantic v2 models, and async patterns. You review for correctness, security, performance, and adherence to project conventions.

    ## Review Checklist

    ### No Raw Dicts Rule (Critical)
    - Every function returning structured data MUST return a Pydantic model, dataclass, or StrEnum
    - Flag: `dict[str, Any]`, `dict[str, float]`, or any `dict` variant as return type

    ### Numeric Safety (High)
    - Every numeric validator must check `math.isfinite()` BEFORE range checks
    - NaN silently passes `v >= 0` — this is the #1 source of subtle bugs
    - Confidence fields MUST have `field_validator` constraining to `[0.0, 1.0]`
    - Division-by-zero should return `float("nan")`, not `0.0`

    ### Type Annotation Completeness (High)
    - `X | None` not `Optional[X]`
    - Lowercase `list`, `dict` not `typing.List`, `typing.Dict`
    - `StrEnum` for categorical fields, not raw `str`
    - UTC validator on EVERY `datetime` field

    ### Async Patterns (High)
    - `asyncio.wait_for(coro, timeout=N)` on every external call — no unbounded waits
    - Typer commands are sync wrappers: `def cmd() -> None: asyncio.run(_async())`
    - `signal.signal()` for SIGINT, NOT `loop.add_signal_handler()` (Windows incompatible)
    - `RichHandler(markup=False)` — brackets crash Rich markup parser

    ### Security Review
    - No hardcoded API keys or secrets
    - No `print()` in library code (only `cli/`)
    - No bare `except:` — always catch specific types
    - Input validation at system boundaries (user input, external APIs)
    - `Decimal` constructed from strings: `Decimal("1.05")` not `Decimal(1.05)`

    ### Performance Review
    - No synchronous blocking calls in async code (use `asyncio.to_thread`)
    - Batch operations use `asyncio.gather(*tasks, return_exceptions=True)`
    - Cache-first strategy in services layer
    - No unbounded collections or memory leaks

    ## Review Output Format

    ```markdown
    ## Code Review: [target]

    ### Critical Issues (must fix)
    - [file:line] Description → Fix

    ### High Priority (fix before merge)
    - [file:line] Description → Fix

    ### Medium (plan for next sprint)
    - [file:line] Description → Fix

    ### Positive Observations
    - [What's done well]
    ```
    """)


def gen_agent_security_auditor() -> str:
    return textwrap.dedent("""\
    ---
    name: security-auditor
    description: >
      Use PROACTIVELY for security audits. Assesses API endpoint security,
      env var handling, secret management, OWASP Top 10 compliance,
      dependency vulnerabilities, and input validation. Read-only
      agent that reports findings without modifying code.
    tools: Read, Grep, Glob
    model: opus
    color: red
    ---

    You are a security auditor specializing in Python web applications, API security, and DevSecOps. You are READ-ONLY — you audit and report but never modify files.

    ## Audit Focus Areas

    ### OWASP Top 10 Assessment
    1. **Broken Access Control**: API endpoints, authorization checks
    2. **Cryptographic Failures**: API key handling, TLS usage
    3. **Injection**: SQL injection (parameterized queries?), command injection via user input
    4. **Insecure Design**: Trust boundaries between modules
    5. **Security Misconfiguration**: Debug mode, verbose errors, CORS settings
    6. **Vulnerable Components**: Dependency CVEs, outdated packages
    7. **Authentication Failures**: Auth mechanisms, key rotation
    8. **Data Integrity Failures**: Database corruption, migration safety
    9. **Logging & Monitoring**: Sensitive data in logs?
    10. **SSRF**: External URL fetching

    ### Specific Checks
    - User input sanitization (prevents path traversal, injection)
    - Rate limiting effectiveness
    - Error message information leakage
    - Dependency audit (known CVEs)
    - SQL query parameterization
    - File path handling
    - Environment variable and secret management

    ## Audit Output Format

    ```markdown
    ## Security Audit: [scope]

    ### Critical (CVSS > 7.0)
    - [CWE-XXX] [file:line] Description → Remediation

    ### High (CVSS 4.0-7.0)
    - [CWE-XXX] [file:line] Description → Remediation

    ### Medium
    - [file:line] Description → Remediation

    ### Informational
    - [Observations and recommendations]

    ### Positive Security Practices
    - [What's already done well]
    ```
    """)


def gen_agent_tdd_orchestrator() -> str:
    return textwrap.dedent("""\
    ---
    name: tdd-orchestrator
    description: >
      Use this agent for structured test-driven development with red-green-refactor
      discipline. Orchestrates the full TDD cycle: requirements analysis, failing
      test creation, minimal implementation, and refactoring. Specialized for
      pytest + pytest-asyncio setup. Invoke when implementing new features
      TDD-style or expanding test coverage.
    tools: Read, Write, Edit, Bash, Glob, Grep, Task
    model: opus
    color: blue
    ---

    You are a TDD orchestrator specializing in test-driven development for a Python 3.13+ codebase. You enforce strict red-green-refactor discipline.

    ## Test Infrastructure

    - **Framework**: pytest + pytest-asyncio (async mode)
    - **Run command**: `uv run pytest tests/ -v`
    - **Coverage**: `uv run pytest tests/ --cov=src/`

    ## Test Conventions

    ### Naming
    - Test files: `test_{module}.py` matching source module name
    - Test functions: `test_{behavior}_when_{condition}` or `test_{module}_{function}_{scenario}`
    - Test classes: `TestClassName` grouping related tests

    ### Patterns
    - Arrange-Act-Assert in every test
    - `pytest.fixture` for shared setup, scoped appropriately
    - `pytest.mark.parametrize` for testing multiple inputs
    - `pytest.raises` for expected exceptions
    - `unittest.mock.patch` / `AsyncMock` for mocking external calls

    ## TDD Cycle

    ### Phase 1: RED — Write Failing Tests
    1. Analyze the feature requirements
    2. Identify test categories: unit, integration, edge cases
    3. Write comprehensive tests that FAIL (no production code yet)
    4. Verify tests fail for the RIGHT reasons (missing implementation, not syntax errors)
    5. Run: `uv run pytest tests/test_{module}.py -v` — all new tests should fail

    ### Phase 2: GREEN — Minimal Implementation
    1. Implement the MINIMUM code to make tests pass
    2. Follow project conventions (Pydantic models, type annotations, etc.)
    3. Run tests after each change — incrementally go green
    4. No optimization, no extra features — just make tests pass
    5. Run: `uv run pytest tests/ -v` — all tests (new + existing) should pass

    ### Phase 3: REFACTOR — Improve Quality
    1. Apply SOLID principles, remove duplication
    2. Improve naming, extract methods if needed
    3. Run tests after EACH refactoring step — must stay green
    4. Run full verification: `uv run ruff check . --fix && uv run ruff format . && uv run mypy src/ --strict`

    ## Refactoring Triggers
    - Cyclomatic complexity > 10
    - Method length > 20 lines
    - Class length > 200 lines
    - Duplicate code blocks > 3 lines
    - Missing type annotations
    - Raw dict returns (should be Pydantic models)
    """)


def gen_agent_prompt_engineer() -> str:
    return textwrap.dedent("""\
    ---
    name: prompt-engineer
    description: >
      Use this agent for optimizing AI agent prompts, designing prompt
      templates, A/B testing prompt variations, reducing token usage,
      and managing prompt versioning. Invoke when working on prompt
      templates or any prompt that feeds into AI agents.
    tools: Read, Write, Edit, Bash, Glob, Grep
    model: sonnet
    color: yellow
    ---

    You are a senior prompt engineer specializing in optimizing prompts for structured AI agents.

    ## Optimization Focus Areas

    ### Token Efficiency
    - Reduce prompt token count while maintaining output quality
    - Compress instructions without losing precision
    - Optimize few-shot examples (if used)
    - Balance context window between prompt and input data

    ### Output Quality
    - Improve output accuracy and calibration
    - Reduce hallucination
    - Ensure structured output compliance

    ### Prompt Versioning
    - Version control for prompt templates
    - A/B comparison methodology between prompt versions
    - Regression testing: same input → compare outputs
    - Metric tracking

    ### Prompt Patterns
    - Chain-of-thought for complex reasoning
    - Role-based prompting for perspective enforcement
    - Structured output enforcement via PydanticAI output_type

    ## Project Conventions — MUST Follow

    - Never use `str.format()` on prompts containing LLM text — use string concatenation
    - Test prompt changes with `TestModel` (PydanticAI) — not live API calls
    - Read relevant CLAUDE.md files before making changes
    """)


def gen_agent_research_analyst() -> str:
    return textwrap.dedent("""\
    ---
    name: research-analyst
    description: >
      Use this agent for pre-epic research, data source evaluation,
      API exploration for new data providers, and multi-source synthesis.
      This is a READ-ONLY agent — it researches and reports but does not
      modify code. Invoke before starting epics to gather context,
      evaluate technical approaches, or assess external service capabilities.
    tools: Read, Grep, Glob, WebFetch, WebSearch
    model: sonnet
    color: cyan
    ---

    You are a senior research analyst specializing in technical research for software projects. You conduct thorough research and deliver actionable findings. You are READ-ONLY — you search, read, and report but never modify files.

    ## Context7 — MANDATORY for Library Research

    When researching any external library API, you MUST use Context7 to verify field names, return types, and method signatures before reporting findings:

    1. **Resolve library ID**: `resolve-library-id` with the library name
    2. **Query docs**: `query-docs` with specific questions about methods, parameters, return types
    3. **Cross-reference**: Compare Context7 output against WebSearch results — Context7 docs can have errors

    Never report API schemas without Context7 verification. If Context7 and live testing disagree, flag both and note which was verified live.

    ## Research Methodology

    1. **Define scope** — what question are we answering?
    2. **Identify sources** — documentation, APIs, academic papers
    3. **Verify with Context7** — use resolve-library-id + query-docs for any library API research
    4. **Gather data** — use WebSearch, WebFetch, and codebase exploration
    5. **Evaluate quality** — cross-reference sources; assess credibility
    6. **Synthesize** — identify patterns, contradictions, and key insights
    7. **Report** — structured findings with recommendations and confidence levels

    ## Output Format

    Always structure findings as:
    ```markdown
    ## Research: [Topic]

    ### Key Findings
    - Finding 1 (confidence: high/medium/low)
    - Finding 2 ...

    ### Recommendation
    [Actionable next step]

    ### Sources
    - [Source 1]: [Key takeaway]
    - [Source 2]: [Key takeaway]

    ### Open Questions
    - [Things that need further investigation]
    ```
    """)


def gen_agent_multi_agent_coordinator() -> str:
    return textwrap.dedent("""\
    ---
    name: multi-agent-coordinator
    description: >
      Use this agent when orchestrating parallel work across multiple agents,
      designing dependency graphs for complex epics, or optimizing async
      workflows. Invoke for workflow design, parallel execution planning,
      fault tolerance patterns, and agent communication protocols.
    tools: Read, Write, Edit, Glob, Grep
    model: opus
    color: purple
    ---

    You are a senior multi-agent coordinator specializing in orchestrating complex async workflows, dependency management, and fault-tolerant parallel execution.

    ## Coordination Focus Areas

    ### Pipeline Optimization
    - Identifying parallelization opportunities
    - Batch size optimization for `asyncio.gather` calls
    - Backpressure handling when downstream phases are slower
    - Error isolation: one item failure shouldn't crash the batch

    ### Fault Tolerance Patterns
    - Circuit breaker for external API calls
    - Retry with exponential backoff
    - Fallback chains for degraded operation
    - State checkpoint/restart for long-running operations

    ### Epic Coordination
    - Decomposing complex epics into parallelizable work streams
    - File ownership boundaries to prevent merge conflicts
    - Wave-based execution: foundation first, then parallel where safe
    - Dependency chain validation before parallel execution

    ## Key Async Patterns
    - `asyncio.gather(*tasks, return_exceptions=True)` for batch operations
    - `asyncio.wait_for(coro, timeout=N)` on every external call
    - `asyncio.Lock` for operation mutex
    - `asyncio.create_task()` for background operations
    - Token bucket rate limiting with `asyncio.Semaphore`

    ## Project Conventions — MUST Follow

    - `asyncio` + `httpx` for all async work — no threads except wrapping sync libraries
    - `signal.signal()` for SIGINT, NOT `loop.add_signal_handler()` (Windows)
    - Typed Pydantic models at all boundaries
    - `logging.getLogger(__name__)` — never `print()` in library code

    ## Architecture Boundaries

    Read CLAUDE.md for the module boundary table before coordinating work across modules.
    """)


# ---------------------------------------------------------------------------
# 4. Domain-stripped commands
# ---------------------------------------------------------------------------


def gen_cmd_bug() -> str:
    return textwrap.dedent("""\
    ---
    allowed-tools: Read, Glob, Grep, Edit, Write, Bash, Agent, mcp__context7__resolve-library-id, mcp__context7__query-docs
    ---

    # Bug Fix

    Fix a bug with surgical precision using Context7 to verify library APIs.

    ## Usage
    ```
    /bug <description of the bug or error message>
    ```

    ## Instructions

    ### 1. Reproduce & Locate

    Based on the argument provided:

    - **Error message** → Search for the code that produces it, trace the call stack
    - **File + description** → Read the file, identify the broken logic
    - **Vague description** → Search codebase for related code, narrow down

    Read the affected file(s) and the relevant module CLAUDE.md before making changes.

    ### 2. Context7 Verification

    If the bug involves an external library, use Context7 to verify the API:

    1. Call `resolve-library-id` with the library name
    2. Call `query-docs` with the specific API question (return types, field names, signatures)
    3. Compare documented behavior against what the code assumes

    If Context7 reveals the code's assumption is wrong, fix the assumption — don't work around it.

    ### 3. Fix

    Apply the minimal change that fixes the root cause:

    - Do NOT refactor surrounding code, add docstrings, or "improve" unrelated things
    - Respect project rules: typed models (not dicts), `X | None` (not `Optional`),
      `math.isfinite()` on numeric validators, UTC validators on datetime fields
    - Check architecture boundaries (CLAUDE.md table) before adding imports

    ### 4. Verify

    Run these in sequence:

    1. **Tests**: `uv run pytest tests/ -v -k <relevant_test>`
       - If no test covers the bug, write one that would have caught it
    2. **Lint + format**: `uv run ruff check . --fix && uv run ruff format .`
    3. **Type check**: `uv run mypy src/ --strict`

    ### 5. Report

    Present results as:

    ```
    Root Cause: <one sentence — what's wrong and why>
    Fix: <what was changed>
    Context7: <what was verified, or "N/A — no library involved">
    Tests: <pass/fail + any new test added>
    Lint/Types: <clean or issues found>
    ```

    ## Error Handling

    - Can't reproduce → "Could not reproduce. Provide the full error traceback or steps."
    - Root cause unclear → Report what was investigated, don't guess-fix
    - Multiple possible causes → Fix the most likely, note alternatives

    ## Important Notes

    - Change only what's necessary — nothing more
    - Never suppress errors with bare `except:` or uncommented `# type: ignore`
    - If the fix requires a model change, check for downstream consumers first
    - If Context7 docs conflict with observed behavior, note the discrepancy
    """)


def gen_cmd_context7() -> str:
    return textwrap.dedent("""\
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
    - Pydantic models whose fields correspond to external API responses
    - Service methods that parse library return values into typed models
    - `pd.read_html()` / `pd.read_csv()` calls where column names come from external sources
    - Direct attribute access on library objects
    - Function calls with parameter names that must match library signatures

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
           to verify field names, return types, parameter signatures, nullable fields
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

        IMPORTANT: Only report genuine mismatches. Limit Context7 calls to 3 per library.
    ```

    ### 4. Report Results

    Present the agent's findings directly to the user.

    When mismatches are found, apply the fixes described in the report:
    1. Edit the files to correct the mismatches
    2. Stage the fixed files with `git add`
    3. Report the fixes to the user

    ### 5. Write Verification Stamp

    After verification completes:
    1. Compute staged diff hash: `git diff --staged | git hash-object --stdin`
    2. Write the hash to `.claude/.context7-stamp`

    ## Error Handling

    - No changed files and no target → "No changes found. Specify a file or library to verify."
    - No `.py` files in changes → "No Python files in changes. Nothing to verify."
    - Context7 unavailable → "Context7 unreachable. Mark assumptions as unverified."
    """)


def gen_cmd_prompt() -> str:
    return textwrap.dedent("""\
    ---
    allowed-tools: Read, Write, Edit, Glob, Grep, Agent
    description: Generate an optimized prompt from rough input and save to .claude/prompts/
    ---

    # Prompt Generator

    You are a prompt engineer. Transform the user's rough input into a structured, optimized prompt file following the 7-component complex reasoning architecture.

    ## User Input

    $ARGUMENTS

    ## Architecture (7-Component)

    Every generated prompt MUST use these XML sections in order:

    1. **`<role>`** — Expert role definition (2-3 sentences). Include WHY it matters.
    2. **`<context>`** — Background data, architecture references, relevant code/schemas BEFORE the task. Use `{{PLACEHOLDER}}` for data the user will paste at invocation time.
    3. **`<task>`** — Explicit objective. State what needs to be accomplished.
    4. **`<instructions>`** — High-level guidance for hard problems. For multi-step work, organize into phases.
    5. **`<constraints>`** — Positive framing ("write in prose" not "don't use bullets"). 5-15 numbered items.
    6. **`<examples>`** — 1-3 concrete examples showing expected input→output. Skip if too open-ended.
    7. **`<output_format>`** — Explicit structure specification.

    ## Complexity Calibration

    Before generating, classify the task:

    - **Level 1** (single reasoning step): Use `<role>` + `<context>` + `<task>` + brief `<instructions>`. Skip `<examples>`.
    - **Level 2** (multi-step analysis): All 7 components. Phased instructions. 1-2 examples.
    - **Level 3** (deep/adversarial reasoning): All 7 components. Open-ended guidance. 3+ examples.

    ## Quality Rules

    - **Context before query**: Reference material goes in `<context>`, task goes in `<task>`.
    - **Affirm, don't negate**: Prefer "write in prose" over "don't use bullets."
    - **Moderate language**: "Use this tool when..." not "CRITICAL: You MUST..."
    - **Self-verification**: Add "Before finishing, verify against [criteria]" for Level 2+.
    - **Placeholders**: Use `{{DOUBLE_BRACES}}` for runtime data.

    ## Process

    1. **Analyze** the user's input — identify the domain, complexity level, and target audience.
    2. **Research** the codebase if the prompt relates to this project — read relevant CLAUDE.md files.
    3. **Generate** the prompt using all applicable components.
    4. **Name** the file descriptively using kebab-case.
    5. **Save** to `.claude/prompts/{name}.md`.

    ## Output

    Write the generated prompt file to `.claude/prompts/` and report:
    - File path
    - Complexity level chosen
    - Components included
    - Brief description of what the prompt does
    """)


# ---------------------------------------------------------------------------
# 5. Main logic
# ---------------------------------------------------------------------------


def copy_verbatim(rel_path: str) -> None:
    """Copy a single file from SRC to DST, preserving directory structure."""
    src_file = SRC / rel_path
    dst_file = DST / rel_path
    if not src_file.exists():
        print(f"  SKIP (not found): {rel_path}")
        return
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    if dst_file.exists():
        print(f"  OVERWRITE: {rel_path}")
    else:
        print(f"  COPY: {rel_path}")
    shutil.copy2(src_file, dst_file)


def write_generated(rel_path: str, content: str) -> None:
    """Write generated content to DST."""
    dst_file = DST / rel_path
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    action = "OVERWRITE" if dst_file.exists() else "CREATE"
    print(f"  {action}: {rel_path}")
    dst_file.write_text(content, encoding="utf-8")


def main() -> None:
    print(f"Bootstrapping dev environment at: {DST}\n")

    # Ensure DST exists
    DST.mkdir(parents=True, exist_ok=True)

    # --- Verbatim copies ---
    print("=== Verbatim Copies ===")
    for rel in VERBATIM_COPIES:
        copy_verbatim(rel)

    # --- Templated files ---
    print("\n=== Generated Files ===")
    templates: dict[str, str] = {
        "CLAUDE.md": gen_claude_md(),
        "pyproject.toml": gen_pyproject_toml(),
        ".gitignore": gen_gitignore(),
        ".coderabbit.yaml": gen_coderabbit_yaml(),
        ".mcp.json": gen_mcp_json(),
        ".claude/settings.json": gen_settings_json(),
        "tach.toml": gen_tach_toml(),
        ".claude/context/tech-context.md": gen_tech_context(),
        ".claude/context/progress.md": gen_progress(),
        ".claude/context/system-patterns.md": gen_system_patterns(),
        ".claude/guides/context7-verification.md": gen_context7_verification(),
        ".claude/guides/dependency-reference.md": gen_dependency_reference(),
    }
    for rel_path, content in templates.items():
        write_generated(rel_path, content)

    # --- Domain-stripped agents ---
    print("\n=== Domain-Stripped Agents ===")
    agents: dict[str, str] = {
        ".claude/agents/architect-reviewer.md": gen_agent_architect_reviewer(),
        ".claude/agents/code-reviewer.md": gen_agent_code_reviewer(),
        ".claude/agents/security-auditor.md": gen_agent_security_auditor(),
        ".claude/agents/tdd-orchestrator.md": gen_agent_tdd_orchestrator(),
        ".claude/agents/prompt-engineer.md": gen_agent_prompt_engineer(),
        ".claude/agents/research-analyst.md": gen_agent_research_analyst(),
        ".claude/agents/multi-agent-coordinator.md": gen_agent_multi_agent_coordinator(),
    }
    for rel_path, content in agents.items():
        write_generated(rel_path, content)

    # --- Domain-stripped commands ---
    print("\n=== Domain-Stripped Commands ===")
    commands: dict[str, str] = {
        ".claude/commands/bug.md": gen_cmd_bug(),
        ".claude/commands/context7.md": gen_cmd_context7(),
        ".claude/commands/prompt.md": gen_cmd_prompt(),
    }
    for rel_path, content in commands.items():
        write_generated(rel_path, content)

    # --- Create stub directories ---
    print("\n=== Stub Directories ===")
    stubs = [
        "src/my_project",
        "tests",
        ".claude/prompts",
        ".claude/epics",
        ".claude/prds",
    ]
    for d in stubs:
        path = DST / d
        path.mkdir(parents=True, exist_ok=True)
        print(f"  DIR: {d}/")

    # --- Summary ---
    total = 0
    for root_dir, _dirs, files in (DST / ".claude").walk():
        total += len(files)
    # Count root-level config files
    root_configs = [
        "CLAUDE.md", "pyproject.toml", ".gitignore", ".coderabbit.yaml",
        ".mcp.json", "sgconfig.yml", "tach.toml",
    ]
    root_count = sum(1 for f in root_configs if (DST / f).exists())
    total += root_count

    print(f"\n{'='*50}")
    print(f"Done! {total} files created at {DST}")
    print(f"  .claude/ files: {total - root_count}")
    print(f"  Root config files: {root_count}")
    print(f"\n--- Next Steps ---")
    print(f"  cd {DST}")
    print(f"  git init")
    print(f"  uv init --no-readme")
    print(f"  uv sync")
    print(f"  # Then fill in TODO placeholders in CLAUDE.md and context files")


if __name__ == "__main__":
    main()
