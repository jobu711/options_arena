# CLAUDE.md — Reporting

## Purpose
Generate Markdown export from debate verdicts. Single file module.

## Files
| File | Purpose |
|------|---------|
| `debate_export.py` | Markdown export for `DebateResult` — pure function, no I/O |
| `__init__.py` | Re-exports `export_debate_markdown`, `export_debate_to_file` |

## Output Format
- **Markdown only** (GitHub-flavored). PDF via optional `weasyprint` in CLI.

## Disclaimer — Removed (AUDIT-010)
No disclaimer text in exports, CLI, or any rendering path.

## What Claude Gets Wrong
- Don't generate reports without metadata block
- Don't add disclaimer text (removed AUDIT-010)
- Don't show raw Greeks without dollar-impact interpretation
- Don't use raw dicts — all report I/O uses typed Pydantic models
