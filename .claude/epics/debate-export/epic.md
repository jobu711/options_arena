---
name: debate-export
status: backlog
created: 2026-02-24T21:49:24Z
progress: 0%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 7: Export Debate Results

## Overview

Debate results are displayed in terminal and persisted to SQLite but cannot be shared or
reviewed offline. This epic adds markdown and optional PDF export via `--export` flag.

## Scope

### PRD Requirements Covered
FR-C2 (Export Debate Results)

### The Elegant Approach

**Pure functions, no framework.** `export_debate_markdown()` is a pure function:
`DebateResult -> str`. It templates the result fields into structured markdown. No
templating library needed — f-strings are sufficient for this structured data.

**PDF via optional `weasyprint`.** PDF export converts the markdown to HTML (via a
minimal HTML wrapper), then renders to PDF with `weasyprint`. If `weasyprint` is not
installed, warn and skip — never crash.

**Architecture boundary**: Export functions go in `reporting/` (can access `models/` only).
The CLI calls export functions after rendering to terminal.

### Deliverables

**`src/options_arena/reporting/__init__.py`** — Re-exports with `__all__`.

**`src/options_arena/reporting/debate_export.py`** — Two functions:

```python
def export_debate_markdown(result: DebateResult) -> str:
    """Render DebateResult as structured markdown."""
    # Template all panels: Bull, Bear, [Vol], [Rebuttal], Verdict
    # Include disclaimer, metadata (duration, tokens, model)
    ...

def export_debate_to_file(result: DebateResult, path: Path, fmt: str = "md") -> Path:
    """Write debate result to file. fmt='md' or 'pdf'."""
    md_content = export_debate_markdown(result)
    if fmt == "md":
        path.write_text(md_content, encoding="utf-8")
        return path
    if fmt == "pdf":
        return _render_pdf(md_content, path)
    raise ValueError(f"Unsupported format: {fmt}")

def _render_pdf(md_content: str, path: Path) -> Path:
    """Convert markdown to PDF via weasyprint. Raises ImportError if not installed."""
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "PDF export requires weasyprint. Install: uv add 'options-arena[pdf]'"
        ) from None
    html = f"<html><body><pre>{md_content}</pre></body></html>"
    HTML(string=html).write_pdf(str(path))
    return path
```

**Markdown format:**

```markdown
# Options Arena Debate Report: {TICKER}
**Date**: {date} | **Duration**: {duration}s | **Model**: {model}
**Fallback**: {yes/no}

## Bull Case (Confidence: {conf:.0%})
{argument}
### Key Points
- {point1}
### Risks Cited
- {risk1}

## Bear Case (Confidence: {conf:.0%})
...

## Volatility Assessment (if present)
...

## Bull Rebuttal (if present)
...

## Verdict
**Direction**: {direction} | **Confidence**: {conf:.0%}
**Strategy**: {strategy or "None"}
{summary}
### Risk Assessment
{risk_assessment}

---
*Disclaimer: This is AI-generated analysis for educational purposes only...*
```

**`src/options_arena/cli/commands.py`** — Add flags:

```python
export: str | None = typer.Option(None, "--export", help="Export format: md or pdf"),
export_dir: str = typer.Option("./reports", "--export-dir", help="Export output directory"),
```

After debate completes, if `--export` is set:

```python
if export:
    from options_arena.reporting import export_debate_to_file
    export_path = Path(export_dir) / f"debate_{ticker}_{date.today().isoformat()}.{export}"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_debate_to_file(result, export_path, fmt=export)
    err_console.print(f"[green]Exported: {export_path}[/green]")
```

With `--batch --export md`: one file per ticker + combined summary file.

**`pyproject.toml`** — Add optional dependency:

```toml
[project.optional-dependencies]
pdf = ["weasyprint>=63.0"]
```

### Tests (~8)
- `export_debate_markdown()` contains all section headers
- Markdown includes vol thesis when present
- Markdown includes rebuttal when present
- Markdown includes fallback warning when `is_fallback=True`
- `export_debate_to_file()` writes markdown to temp path
- PDF export raises `ImportError` when weasyprint not installed
- Export directory created automatically
- Batch export: per-ticker files created

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 6 (batch mode for combined reports)
- **Blocks**: Nothing (terminal epic)

## Key Decision
PDF export wraps markdown in `<pre>` HTML. This is intentionally minimal — fancy HTML
templating with CSS is deferred. The markdown export is the primary format; PDF is a
convenience for users who need it.
