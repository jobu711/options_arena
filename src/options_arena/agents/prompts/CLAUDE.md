<claude_instructions>
# CLAUDE.md — Debate Prompt Templates

## Purpose
System prompts and templates for the AI debate agents. Every prompt is versioned,
every market data injection is structured, every user input is sanitized.

## Files
- `loader.py` — loads templates + renders with market data
- `versions.py` — version registry (maps tags to template files)
- `templates/` — `.txt` files for each role

## Versioning Is Mandatory
- Header in every template: `# VERSION: v1.2`
- Log version used in every debate round and final report.
- Never overwrite — increment version, keep old ones accessible.

## Template Structure — Options-Specific
```text
# VERSION: v1.0

## Role
You are a {position} options analyst.

## Objective
Argue the {position} case for {option_type} options on {ticker} at the ${strike} strike
expiring {expiration} ({dte} DTE).

## Market Context
{market_context_block}

## Constraints
- Reference SPECIFIC strikes, expirations, and Greeks — not just directional opinion.
- Cite IV Rank/Percentile to justify whether options are cheap or expensive.
- Address theta decay impact given the DTE.
- Quantify max profit, max loss, and breakeven for your recommended position.
- Acknowledge the strongest counter-argument.
- Do not fabricate data. If not provided, say so.
- {max_words} words max.

## Output Format
1. Thesis (1-2 sentences with specific contract)
2. Supporting Evidence (3-5 points citing Greeks, IV, indicators)
3. Risk (1-2 key risks with quantified impact)
4. Strategy (specific spread/position with max profit, max loss, breakeven)
5. Conviction (low/medium/high with justification)
```

## Market Context Block — Flat Key-Value Only
```text
Current Price: $185.42
52-Week Range: $124.17 - $199.62
IV Rank: 72.3 (high — options are expensive relative to past year)
IV Percentile: 85.1%
ATM IV (30 DTE): 38.2%
RSI(14): 68.2 (approaching overbought)
MACD: Bullish crossover 3 days ago
Put/Call Ratio (volume): 0.82
Next Earnings: 2025-04-24 (32 DTE)
Target Strike: $190 call
Delta: 0.45 | Gamma: 0.032 | Theta: -$0.08/day | Vega: 0.15
Bid: $4.20 | Ask: $4.50 | Spread: $0.30
Open Interest: 12,450
Data as of: 2025-03-15 14:30 UTC
```
Never inject raw JSON. Models parse labeled key-value pairs better.
Always include data timestamp.

## Rebuttal Rounds
Wrap opponent text in delimiters so models don't confuse it with instructions:
```text
## Opponent's Argument
<opponent_argument>
{opponent_text}
</opponent_argument>

## Your Task
Rebut the above. Strengthen your position with specific contract data.
```

## Moderator Prompt
- Receives FULL transcript (all rounds, both sides).
- Must evaluate: argument quality + data specificity, not style.
- Must output: winner, confidence (0-100), reasoning, recommended strategy, risk assessment.
- Must declare a draw if neither side is convincingly stronger.
- Must evaluate whether each side properly addressed Greeks, IV, and theta risk.

## Prompt Injection Prevention
- Sanitize ticker symbols and user notes before injection.
- Wrap user input: `<user_input>{text}</user_input>`.
- User input never becomes part of system instructions.

## Token Budget
- System prompts: <1500 tokens. Context block adds 300-500.
- Monitor total tokens per round. If transcript exceeds 70% of context, summarize older rounds.
- For small Ollama models (<13B), maintain simplified prompt variants — shorter, less structure.

## What Claude Gets Wrong Here (Fix These)
- Don't inject raw JSON as context — flat key-value only.
- Don't forget to version prompts — unversioned = undebuggable.
- Don't let opponent text bleed into instructions — use delimiters.
- Don't use verbose Claude prompts for small Ollama models — maintain simplified variants.
- Don't let token budget grow unbounded over rounds.
- Don't write prompts that accept vague directional opinions — enforce contract-specific claims.
</claude_instructions>
