# CLAUDE.md -- Reporting

## Purpose

Generate Markdown export from debate verdicts and recommendations. Pure functions, no I/O.

## Output Format

- **Markdown only** (GitHub-flavored). PDF via optional `weasyprint` in CLI.
- No disclaimer text in exports (removed AUDIT-010).

## What Claude Gets Wrong

- Don't generate reports without metadata block
- Don't add disclaimer text (removed AUDIT-010)
- Don't show raw Greeks without dollar-impact interpretation
- Don't use raw dicts -- all report I/O uses typed Pydantic models
