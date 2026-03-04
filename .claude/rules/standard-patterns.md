# Standard Patterns

## Core Principles

1. **Fail Fast** — Check critical prerequisites, then proceed
2. **Trust the System** — Don't over-validate things that rarely fail
3. **Clear Errors** — When something fails, say exactly what and how to fix it
4. **Minimal Output** — Show what matters, skip decoration

## Error Format

```
{What failed}: {Exact solution}
Example: "Epic not found: Run /pm:prd-parse feature-name"
```

## Output Formats

- **Success**: `{Action} complete` + key results + `Next: {suggested action}`
- **List**: `{Count} {items} found:` + bulleted items with key details
- **Progress**: `{Action}... {current}/{total}`

## Status Indicators

- Success (use sparingly)
- Error (always with solution)
- Warning (only if action needed)
- No emoji for normal output

## Workflow-Specific Guides

- DateTime formatting: `.claude/guides/datetime.md`
- GitHub CLI operations: `.claude/guides/github-operations.md`
