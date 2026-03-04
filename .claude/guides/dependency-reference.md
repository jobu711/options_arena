# Dependency Reference

Full version pinning for web, optional, and dev dependencies. Runtime Python deps
are in `tech-context.md`. Check `pyproject.toml` and `web/package.json` for latest.

## Web Runtime (`web/package.json`)

| Package | Version | Purpose |
|---------|---------|---------|
| vue | ^3.5.29 | SPA framework (Composition API + `<script setup>`) |
| vue-router | ^5.0.3 | Client-side routing (8 routes, lazy-loaded) |
| pinia | ^3.0.4 | State management (scan, debate, health, operation, watchlist stores) |
| primevue | ^4.5.4 | UI component library (DataTable, Dialog, Toast, Drawer) |
| @primeuix/themes | ^2.0.3 | Aura dark theme preset |
| vite | ^7.3.1 | Dev server + build tool |
| typescript | ^5.9.3 | Type checking (`vue-tsc --noEmit`) |
| @playwright/test | ^1.52.0 | E2E testing (38 tests, 4 parallel workers) |

## Python Web Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.133.1 | REST API + WebSocket backend |
| uvicorn[standard] | >=0.41.0 | ASGI server for FastAPI |

## Optional

| Package | Version | Purpose |
|---------|---------|---------|
| weasyprint | >=63.0 | PDF export (`pip install options-arena[pdf]`) |
| openbb | (external) | Fundamentals, unusual flow, news — guarded imports |
| vaderSentiment | (external) | News sentiment — used by OpenBB service layer |

## Dev

| Package | Version | Purpose |
|---------|---------|---------|
| ruff | >=0.15.1 | Linter + formatter |
| mypy | >=1.19.1 | Type checker (`--strict`) |
| pytest | >=9.0.2 | Test framework |
| pytest-asyncio | >=1.3.0 | Async test support |
| pytest-cov | >=7.0.0 | Coverage reporting |
| pandas-stubs | >=3.0.0.260204 | Type stubs for pandas |
| scipy-stubs | >=1.17.0.2 | Type stubs for scipy |

## Build System

- **Build backend**: Hatchling
- **Source layout**: `src/options_arena/` (src-based layout)
- **Wheel packages**: `["src/options_arena"]`

## Tool Configuration

- **Ruff**: Python 3.13, line-length 99, rules E/F/I/UP/B/SIM/ANN
- **Mypy**: `strict = true`, `warn_return_any = true`, `warn_unused_configs = true`
- **Pytest**: async via pytest-asyncio, custom `integration` marker
