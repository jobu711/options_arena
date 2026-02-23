---
allowed-tools: Task, Read, Glob, Grep, LS, Bash
---

# Code Analyzer

Launch the code-analyzer agent to hunt for bugs, trace logic flow, and review code changes.

## Usage
```
/analyze [target]
```

Where `target` can be:
- Empty (analyze recent git changes)
- File path or glob pattern (analyze specific files)
- Description of a bug or behavior to investigate

## Instructions

### 1. Determine Analysis Scope

Based on the argument provided:

- **No arguments** → Analyze uncommitted changes (`git diff` and `git diff --staged`)
- **File path** → Deep-dive analysis of the specified file(s)
- **Bug description** → Investigate the described behavior across the codebase

### 2. Launch Code Analyzer Agent

Use the Task tool with `subagent_type: code-analyzer`:

#### For recent changes (no arguments):
```markdown
Task:
  description: "Analyze recent changes"
  subagent_type: "code-analyzer"
  prompt: |
    Analyze the recent code changes in this repository.

    1. Run `git diff` and `git diff --staged` to identify all modified files
    2. Read each modified file to understand full context
    3. Trace logic flow across changed files
    4. Hunt for bugs, regressions, and edge cases
    5. Check for security vulnerabilities
    6. Verify error handling completeness
    7. Return findings in the BUG HUNT SUMMARY format
```

#### For specific files:
```markdown
Task:
  description: "Analyze {target}"
  subagent_type: "code-analyzer"
  prompt: |
    Deep-dive analysis of: {target}

    1. Read the target file(s)
    2. Identify all imports and dependencies
    3. Trace logic flow through critical paths
    4. Hunt for bugs, edge cases, and type issues
    5. Check for security vulnerabilities
    6. Cross-reference with related files
    7. Return findings in the BUG HUNT SUMMARY format
```

#### For bug investigation:
```markdown
Task:
  description: "Investigate: {target}"
  subagent_type: "code-analyzer"
  prompt: |
    Investigate the following issue: {target}

    1. Search the codebase for relevant code paths
    2. Trace the logic flow that could cause this behavior
    3. Identify the root cause
    4. Check for related issues in nearby code
    5. Suggest a specific fix
    6. Return findings in the BUG HUNT SUMMARY format
```

### 3. Report Results

Present the agent's findings directly. The code-analyzer agent returns structured output in BUG HUNT SUMMARY format:

```
BUG HUNT SUMMARY
==================
Scope: [files analyzed]
Risk Level: [Critical/High/Medium/Low]

CRITICAL FINDINGS:
- [Issue]: [Description + file:line]

POTENTIAL ISSUES:
- [Concern]: [Description + location]

VERIFIED SAFE:
- [Component]: [What was checked]

RECOMMENDATIONS:
1. [Priority action items]
```

## Error Handling

- No changes found → "No uncommitted changes. Specify a file or pattern to analyze."
- File not found → "❌ Target not found: {target}"
- Analysis incomplete → Report partial findings with note on what couldn't be analyzed

## Important Notes

- The agent reads files directly — no need to paste code
- For large scopes, the agent summarizes aggressively to preserve context
- Findings are prioritized: critical bugs first, then patterns, then minor issues
- False positives are minimized — only confident issues are flagged
