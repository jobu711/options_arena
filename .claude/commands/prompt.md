---
allowed-tools: Read, Write, Edit, Glob, Grep, Agent
description: Generate an optimized prompt from rough input and save to .claude/prompts/
---

# Prompt Generator

You are a prompt engineer. Transform the user's rough input into a structured, optimized prompt file following the 7-component complex reasoning architecture.

## User Input

$ARGUMENTS

## Architecture (7-Component — from complex-reasoning.md)

Every generated prompt MUST use these XML sections in order:

1. **`<role>`** — Expert role definition (2-3 sentences). Include WHY it matters — Claude generalizes from motivation, not just rules.
2. **`<context>`** — Background data, architecture references, relevant code/schemas BEFORE the task. Place long reference material here. Use `{{PLACEHOLDER}}` for data the user will paste at invocation time.
3. **`<task>`** — Explicit objective. State what needs to be accomplished. For complex tasks, break into numbered phases.
4. **`<instructions>`** — High-level guidance for hard problems (not prescriptive step-by-step). For multi-step work, organize into phases (Assess → Design → Decide, or similar). Include decision trees where multiple paths exist.
5. **`<constraints>`** — Positive framing ("write in prose" not "don't use bullets"). Include project-specific rules (architecture boundaries, naming conventions, type rules). Keep to 5-15 numbered items.
6. **`<examples>`** — 1-3 concrete examples showing expected input→output. Include `<thinking>` tags to model reasoning when appropriate. Skip this section if the task is too open-ended for examples.
7. **`<output_format>`** — Explicit structure specification. Define sections, tables, code blocks the output should contain.

## Complexity Calibration

Before generating, classify the task:

- **Level 1** (single reasoning step): Use `<role>` + `<context>` + `<task>` + brief `<instructions>`. Skip `<examples>`.
- **Level 2** (multi-step analysis): All 7 components. Phased instructions. 1-2 examples.
- **Level 3** (deep/adversarial reasoning): All 7 components. Open-ended guidance with multiple frameworks. 3+ examples. Self-verification step in instructions.

## Quality Rules

- **Context before query**: Reference material goes in `<context>`, task goes in `<task>` — never reverse this.
- **Affirm, don't negate**: Prefer "write in prose" over "don't use bullets."
- **Moderate language**: "Use this tool when..." not "CRITICAL: You MUST..." — Claude 4.6 overtriggers on aggressive phrasing.
- **Self-verification**: Add "Before finishing, verify against [criteria]" in instructions for Level 2+ prompts.
- **Quote-grounding**: For prompts that process long context, instruct Claude to quote sources before analyzing.
- **Placeholders**: Use `{{DOUBLE_BRACES}}` for data the user pastes at runtime. Add HTML comments explaining what goes there.

## Options Arena Context

When the prompt relates to this codebase, weave in relevant project conventions:
- Typed models everywhere (never raw dicts)
- `X | None` syntax (never `Optional[X]`)
- Architecture boundary table from CLAUDE.md
- Module-specific rules from that module's CLAUDE.md
- NaN/Inf defense pattern where numeric validation applies

## Process

1. **Analyze** the user's input — identify the domain, complexity level, and target audience.
2. **Research** the codebase if the prompt relates to Options Arena — read relevant CLAUDE.md files, scan existing code patterns, check existing prompts in `.claude/prompts/` to avoid duplication.
3. **Generate** the prompt using all applicable components from the 7-component architecture.
4. **Name** the file descriptively using kebab-case (e.g., `volatility-surface-analysis.md`, `api-endpoint-design.md`).
5. **Save** to `.claude/prompts/{name}.md`.

## Output

Write the generated prompt file to `.claude/prompts/` and report:
- File path
- Complexity level chosen
- Components included
- Brief description of what the prompt does
