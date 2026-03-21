#!/usr/bin/env python3
"""Pre-tool hook: blocks git commit/add when staged files contain potential secrets.

Scans staged diffs for API keys, private keys, and forbidden credential files.
Fires on Bash tool calls containing git commit or git add.

Cross-platform — uses only Python stdlib (no external deps).
"""

import json
import os
import re
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SUBPROCESS_TIMEOUT = 10
_MAX_FILE_SIZE = 50 * 1024  # 50KB per file

# ---------------------------------------------------------------------------
# Secret patterns (high-confidence, project-specific)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"gsk_[a-zA-Z0-9]{20,}"), "Groq API key"),
    (re.compile(r"sk-ant-[a-zA-Z0-9\-]{20,}"), "Anthropic API key"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "OpenAI API key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,}"), "GitHub token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN.*PRIVATE KEY-----"), "Private key block"),
    (re.compile(
        r"""(?:password|secret|token|api_key|apikey)\s*[=:]\s*['"][^'"]{8,}['"]""",
        re.IGNORECASE,
    ), "Password/secret assignment"),
]

# ---------------------------------------------------------------------------
# Forbidden files (always blocked from staging)
# ---------------------------------------------------------------------------

_FORBIDDEN_BASENAMES = frozenset({
    ".env",
    "credentials.json",
    ".mcp.json",
    "id_rsa",
    "id_ed25519",
})

_FORBIDDEN_EXTENSIONS = frozenset({
    ".pem",
    ".key",
    ".p12",
    ".pfx",
})

_FORBIDDEN_PREFIXES = (".env.",)

# ---------------------------------------------------------------------------
# False positive suppressors
# ---------------------------------------------------------------------------

_FALSE_POSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"re\.compile\(", re.IGNORECASE),  # regex pattern definitions, not secrets
    re.compile(r"os\.environ\.get\(", re.IGNORECASE),
    re.compile(r"os\.getenv\(", re.IGNORECASE),
    re.compile(r"getenv\(", re.IGNORECASE),
    re.compile(r"\btest_\w*", re.IGNORECASE),
    re.compile(r"\bmock_\w*", re.IGNORECASE),
    re.compile(r"\bfake_\w*", re.IGNORECASE),
    re.compile(r"\bdummy_\w*", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bexample\b", re.IGNORECASE),
    re.compile(r"\byour-", re.IGNORECASE),
    re.compile(r"GROQ_API_KEY\b"),  # env var name reference, not a value
    re.compile(r"ANTHROPIC_API_KEY\b"),
    re.compile(r"OPENAI_API_KEY\b"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_git(args: list[str]) -> str:
    """Run a git command, return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
            cwd=_PROJECT_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _is_forbidden_file(filepath: str) -> str | None:
    """Check if a file path is a forbidden credential file. Return reason or None."""
    basename = os.path.basename(filepath)

    if basename in _FORBIDDEN_BASENAMES:
        return f"Forbidden credential file: {basename}"

    for prefix in _FORBIDDEN_PREFIXES:
        if basename.startswith(prefix):
            return f"Forbidden credential file: {basename}"

    _, ext = os.path.splitext(basename)
    if ext.lower() in _FORBIDDEN_EXTENSIONS:
        return f"Forbidden key file: {basename}"

    return None


def _is_false_positive(line: str) -> bool:
    """Check if a line is a likely false positive."""
    return any(pat.search(line) for pat in _FALSE_POSITIVE_PATTERNS)


def _scan_line(line: str) -> str | None:
    """Scan a single line for secret patterns. Return description or None."""
    if _is_false_positive(line):
        return None

    for pattern, description in _SECRET_PATTERNS:
        if pattern.search(line):
            return description

    return None


def _scan_staged_diff() -> list[str]:
    """Scan git staged diff for secrets. Returns list of findings."""
    findings: list[str] = []

    # Check for forbidden files in staged changes
    staged_files = _run_git(["diff", "--cached", "--name-only"])
    if staged_files:
        for filepath in staged_files.splitlines():
            reason = _is_forbidden_file(filepath)
            if reason:
                findings.append(reason)

    # Scan added lines in the diff
    diff_output = _run_git(["diff", "--cached", "-U0"])
    if not diff_output:
        return findings

    current_file = ""
    for line in diff_output.splitlines():
        if line.startswith("diff --git"):
            # Extract filename
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) > 1 else ""
            continue

        # Only scan added lines (not removed)
        if not line.startswith("+") or line.startswith("+++"):
            continue

        content = line[1:]  # Strip the leading +
        secret_type = _scan_line(content)
        if secret_type:
            # Truncate the line for the message
            preview = content[:60] + "..." if len(content) > 60 else content
            findings.append(f"{secret_type} in {current_file}: {preview}")

    return findings


def _scan_files_being_added(command: str) -> list[str]:
    """Scan specific files being git-added for forbidden files."""
    findings: list[str] = []

    # Extract file paths from "git add <files>" command
    # Skip broad adds like "git add -A" or "git add ." — defer to commit-time scan
    parts = command.split()
    if not parts:
        return findings

    # Find "add" position
    try:
        add_idx = parts.index("add")
    except ValueError:
        return findings

    files = parts[add_idx + 1:]

    for filepath in files:
        # Skip flags
        if filepath.startswith("-"):
            continue
        # Skip broad adds
        if filepath in (".", "-A", "--all"):
            return []

        reason = _is_forbidden_file(filepath)
        if reason:
            findings.append(reason)

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_name: str = data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input_value = data.get("tool_input", {})
    if not isinstance(tool_input_value, dict):
        sys.exit(0)
    command = tool_input_value.get("command", "")
    if not isinstance(command, str) or not command:
        sys.exit(0)

    findings: list[str] = []

    if "git commit" in command:
        findings = _scan_staged_diff()
    elif "git add" in command:
        findings = _scan_files_being_added(command)
    else:
        sys.exit(0)

    if not findings:
        sys.exit(0)

    # Secrets detected — deny
    finding_text = "; ".join(findings[:5])
    if len(findings) > 5:
        finding_text += f" ... and {len(findings) - 5} more"

    result_json = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by secret-scanner: {finding_text}. "
                "Remove secrets from staged files before committing. "
                "Use environment variables or .env files (which are gitignored)."
            ),
        }
    }
    print(json.dumps(result_json))
    sys.exit(0)


if __name__ == "__main__":
    main()
