# CLAUDE.md -- Agent Prompts (`agents/prompts/`)

## Purpose

Centralized prompt library for desk, recommendation, and synthesis agent system prompts.
Each file exports a single prompt string constant used by the corresponding agent module.

## File Organization

- 7 desk prompt files (`desk_*.py`) -- interactive query mode
- 6 recommendation prompt files (`recommend_*.py`) -- structured assessment mode
- 1 synthesis prompt file (`synthesis.py`) -- synthesis agent

## Rules

1. **One constant per file** -- each file exports exactly one prompt constant
2. **Desk prompts**: conversational tone, NO `PROMPT_RULES_APPENDIX`
3. **Recommendation + Synthesis prompts**: end with `+ PROMPT_RULES_APPENDIX` concatenation
4. **Token budget** -- each prompt < 8000 chars (~2000 tokens)
5. **No business logic** -- prompt files contain only string constants and the appendix import
6. **No service/pricing imports** -- only import from `_parsing.py`
7. **Static only** -- dynamic injection (learned patterns, tuned weights) stays in agent modules

## What Stays in Agent Modules (NOT here)

- `@system_prompt(dynamic=True)` decorators (runtime deps injection)
- `@output_validator` decorators (think-tag stripping)
- `Agent` instances and their configuration
