# Atomic Batch DB Writes — Use commit=False in Loops

## Problem

Calling `await repo.update_*(..., commit=True)` inside a loop issues N individual
COMMIT operations. If the process crashes mid-loop, some rows are updated and others
are not, leaving the database in an inconsistent state.

## Context

Found in `learning/confidence_decay.py` — `_run_decay_pipeline()` updated each rule's
confidence individually with `commit=True` (the default). A crash after rule 50 of 200
would leave 50 rules decayed and 150 untouched, with no promote/demote applied.

## Solution

Pass `commit=False` on each write, then issue a single `await repo.commit()` at the end:

```python
# WRONG — N individual commits
for rule in rules:
    await repo.update_rule_confidence(rule_id=rule.rule_id, confidence=new_conf)

# RIGHT — single atomic commit
for rule in rules:
    await repo.update_rule_confidence(rule_id=rule.rule_id, confidence=new_conf, commit=False)
await repo.commit()
```

## Applies To

- Any loop that performs multiple DB writes within a single logical operation
- Decay pipelines, batch persistence, migration-like operations
- Existing pattern in `scan/phase_persist.py` (reference implementation)

## Related

- `data/CLAUDE.md` — documents `commit=False` kwarg pattern on all mixin methods
- `data/_base.py` — `RepositoryBase.commit()` for explicit commit
