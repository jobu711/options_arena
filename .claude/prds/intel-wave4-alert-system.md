---
name: intel-wave4-alert-system
description: Multi-tier alert system with semantic dedup, decay-based cooldowns, and rate limiting
status: backlog
created: 2026-03-24T15:48:29Z
effort: M
---

# PRD: intel-wave4-alert-system

## Executive Summary

Build a multi-tier alert system that evaluates DeltaReports and generates prioritized alerts (FLASH/PRIORITY/ROUTINE) with semantic dedup, progressive cooldown suppression, and per-tier rate limiting. Alerts are delivered via WebSocket initially, with rule-based evaluation as the primary engine and optional LLM enhancement in future.

## Problem Statement

### What problem are we solving?

The delta engine (Wave 3) detects market changes, but detection without notification is useless. Traders need to be alerted when meaningful shifts occur — especially when they affect open positions or upcoming trades. Without an alert system, users must manually check for changes.

### Why is this important now?

Alert system depends on the delta engine (Wave 3). Intelligence desk agent (Wave 5) and API wiring (Wave 7) depend on alert infrastructure existing for WebSocket delivery.

## Requirements

### Functional Requirements

#### FR-1: Alert Service (`services/alerts.py`)

```python
class AlertService:
    def __init__(self, config: IntelligenceConfig, repo: Repository): ...
    async def evaluate_delta(self, report: DeltaReport) -> list[AlertRecord]: ...
```

**Evaluation pipeline** (for each MetricDelta in DeltaReport):
1. **Tier mapping**: CRITICAL severity → FLASH, HIGH → PRIORITY, MODERATE → ROUTINE
2. **Tier escalation**: 2+ CRITICAL signals across different categories → escalate to FLASH
3. **Fingerprint**: SHA-256 of `f"{category}:{metric_name}:{severity}"` (truncated to 16 chars)
4. **Dedup**: query `alert_history` for recent alerts with same fingerprint within cooldown window
5. **Cooldown**: progressive decay — `base_cooldown * 2^min(cooldown_count, 5)`, capped at 32x base
   - FLASH base: 300s (5 min)
   - PRIORITY base: 3600s (1 hour)
   - ROUTINE base: 14400s (4 hours)
6. **Rate limit**: hourly cap per tier (configurable via IntelligenceConfig)
7. **Persist**: surviving alerts saved to `alert_history` table
8. **Deliver**: push to WebSocket alert queue

**Alert content generation** (rule-based):
- Title: `f"{metric_name}: {direction} {change_pct:.1f}%"` or category-specific templates
- Body: `f"{metric_name} moved from {prev} to {curr} ({change_pct:+.1f}%). {context}."`
- No LLM required for initial implementation

#### FR-2: WebSocket Alert Bridge (`api/ws.py`)

Following existing `WebSocketProgressBridge` pattern:

```python
class AlertBridge:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=100)

    def push_alert(self, alert: AlertRecord) -> None:
        """Push alert to WebSocket queue (sync, uses put_nowait)."""
```

New endpoint: `WS /ws/alerts` — drains alert queue, sends events:
```json
{"type": "alert", "tier": "flash", "title": "...", "body": "...", "severity": "critical", "created_at": "..."}
```

#### FR-3: Alert Acknowledgment

- `POST /api/intelligence/alerts/{id}/ack` → sets status to ACKNOWLEDGED
- Acknowledged alerts are excluded from dedup window
- UI can show/hide acknowledged alerts

### Non-Functional Requirements

- AlertService follows never-raises contract (evaluation failures → empty list, log WARNING)
- Dedup and cooldown queries are indexed (fingerprint, created_at)
- Alert delivery is fire-and-forget (non-blocking for the sweep cycle)
- All config values (cooldowns, caps, thresholds) come from IntelligenceConfig — no magic numbers

## Success Criteria

- Dedup test: same signal twice within cooldown → second suppressed
- Cooldown decay test: 3rd occurrence has 4x base cooldown
- Rate limit test: exceed hourly cap → suppressed
- Tier escalation test: 2 CRITICAL cross-domain → FLASH
- WebSocket test: alert bridge queues events correctly
- `uv run pytest tests/unit/services/test_alerts.py -v` passes

## Out of Scope

- LLM-powered alert text (future enhancement — rule-based is sufficient)
- Email delivery channel (future — WebSocket first)
- Telegram/Discord delivery (future)
- Mobile push notifications

## Dependencies

- **Wave 3** (intel-wave3-delta-engine) — delta reports and alert_history table must exist

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/alerts.py` | **Create** |
| `src/options_arena/services/__init__.py` | Modify — add AlertService export |
| `src/options_arena/api/ws.py` | Modify — add AlertBridge + WS /ws/alerts |
| `tests/unit/services/test_alerts.py` | **Create** |
