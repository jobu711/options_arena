---
title: "joblib.load() path traversal via configurable model_cache_dir"
date: 2026-03-17
module: options_arena.indicators
problem_type: integration_issues
severity: critical
symptoms:
  - "Arbitrary code execution if attacker places crafted .pkl at model path"
  - "model_cache_dir env var override allows loading from outside project root"
tags:
  - security
  - joblib
  - pickle
  - path-traversal
  - deserialization
root_cause: "joblib.load() uses pickle internally — configurable model_cache_dir allows loading .pkl files from arbitrary filesystem locations"
---

## Problem

`indicators/regime_ml.py` uses `joblib.load()` to load a pre-trained ML model from disk.
The model path is derived from `MLConfig.model_cache_dir`, which is configurable via the
`ARENA_SCAN__ML__MODEL_CACHE_DIR` environment variable. No validation prevented loading
from paths outside the project root.

`joblib.load()` uses pickle internally, which can execute arbitrary Python code during
deserialization. If an attacker could:
1. Override `model_cache_dir` via env var to point to an attacker-controlled directory
2. Place a crafted `.pkl` file at the expected path

...they would achieve arbitrary code execution when the ML regime classifier runs.

## Root Cause

Two compounding issues:
1. `joblib.load()` is fundamentally unsafe for untrusted inputs (uses pickle)
2. The model path was configurable without any path validation or sandboxing

## Solution

Added a path traversal guard in `_load_model()` that validates the resolved path is
within the project root before loading:

```python
if path is None:  # Only check default (config-derived) paths
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    if not resolved.resolve().is_relative_to(project_root):
        logger.warning(
            "ML regime model path %s is outside project root — refusing to load",
            resolved,
        )
        return None
```

Key design decisions:
- **Only checks default paths** — explicit caller-provided paths (from tests using
  `tmp_path`) skip the project root check, since those are programmatic, not user-config
- **Uses `Path.resolve().is_relative_to()`** — handles `..` components correctly
- **Logs and returns None** — never raises, consistent with the indicators module's
  "return None on failure" contract

## Prevention Rule

1. **Never use pickle/joblib.load() on user-configurable paths** without validating
   the path resolves within a trusted directory.
2. **Path validation pattern**: `resolved.resolve().is_relative_to(project_root)`
3. **Consider SafeTensors or ONNX** for ML model serialization when security matters.
4. **Test paths from tmp_path bypass the check** — design the guard to distinguish
   config-derived paths (untrusted) from programmatic paths (trusted).

## Related

- P1-5 in `.claude/audits/FULL_AUDIT.md`
- CWE-502 (Deserialization of Untrusted Data)
- CWE-918 (Server-Side Request Forgery)
- `src/options_arena/indicators/regime_ml.py:_load_model()`
