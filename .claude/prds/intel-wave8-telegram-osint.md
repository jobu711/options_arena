---
name: intel-wave8-telegram-osint
description: Telegram public channel OSINT monitoring with urgency scoring — deferred to separate PR
status: deferred
created: 2026-03-24T15:48:29Z
effort: M
---

# PRD: intel-wave8-telegram-osint

## Executive Summary

Scrape public Telegram channel web previews for real-time geopolitical and financial intelligence. Monitor curated OSINT channels (conflict zones, macro commentary, options flow) with keyword-based urgency scoring. Feed urgent signals into the IntelligenceSnapshot for cross-domain correlation.

**Status: DEFERRED** — Lower priority than API-based data sources. Requires careful HTML parsing and rate limit testing. Implement after Waves 1-7 are stable.

## Problem Statement

### What problem are we solving?

Real-time OSINT from Telegram channels (particularly `unusual_whales` for options flow and geopolitical channels for conflict monitoring) provides leading indicators that precede formal news coverage. This data is publicly available via channel web previews at `https://t.me/s/{channel_id}` but requires scraping and urgency classification.

### Why is this important now?

This is an enhancement to the intelligence layer, not a blocker. Waves 1-7 deliver full intelligence capability using structured API data. Telegram adds social/OSINT signal quality. Schedule after core intelligence is proven stable.

## Requirements

### Functional Requirements

#### FR-1: Telegram OSINT Service (`services/telegram_osint.py`)

- **Source**: Public channel web previews at `https://t.me/s/{channel_id}` (no auth required)
- **Methods**:
  - `fetch_osint_snapshot() -> OsintSnapshot | None`
  - `fetch_channel(channel_id: str) -> list[OsintPost] | None`
- **Curated channels** (configurable via `TelegramOsintConfig`):
  - `unusual_whales` — options flow analysis
  - `WallStreetSilver` — commodities/macro commentary
  - `middleeastosint` — Middle East OSINT
  - `wartranslated` — conflict translations
  - Additional channels configurable via env var
- **HTML parsing**: stdlib `html.parser` or `re` — no beautifulsoup4 dependency
- **Urgency scoring**: keyword matching against curated list:
  - Financial: "earnings", "FDA", "buyback", "guidance", "flash crash", "circuit breaker"
  - Military/geopolitical: "missile", "strike", "sanctions", "escalation", "ceasefire"
  - Breaking: "breaking", "urgent", "alert", "confirmed"
- **Rate limiting**: 1.5s delay between channel fetches, batch 3 channels at a time
- **Cache**: TTL 900s (15 min)

#### FR-2: New Models

- `OsintPost` — text, date, channel, views, urgency_score (float), urgency_keywords (list[str])
- `OsintSnapshot` — posts (list[OsintPost]), urgent_posts (list[OsintPost]), channels_monitored (int), fetched_at (UTC)
- `TelegramOsintConfig` — enabled (bool=False), channels (list[str]), urgency_keywords (list[str])

#### FR-3: IntelligenceSnapshot Extension

Add optional `osint: OsintSnapshot | None = None` field to `IntelligenceSnapshot`.
Wire into `IntelligenceCollector.collect_snapshot()`.

### Non-Functional Requirements

- No new pip dependencies (stdlib HTML parsing only)
- Never-raises contract
- Windows compatible
- Graceful degradation: channels that 403/timeout → skip, continue with others

## Success Criteria

- HTML parsing correctly extracts posts from `https://t.me/s/unusual_whales`
- Urgency scoring flags relevant posts
- Integration with IntelligenceSnapshot works
- No impact on existing intelligence flow when disabled

## Out of Scope

- Telegram Bot API integration (requires bot token setup)
- Reddit OAuth integration (separate PRD if needed)
- Bluesky AT Protocol integration (separate PRD if needed)
- Real-time streaming (polling every 15 min is sufficient)

## Dependencies

- **Waves 1-3** (foundation, data sources, collector) — must be stable

## Deferred Items Noted for Future Backlog

| Item | Notes |
|------|-------|
| Reddit social sentiment | OAuth app registration required. Subreddits: wallstreetbets, options, commodities. |
| Bluesky sentiment | Public AT Protocol search API, no auth. Low signal quality for options currently. |
| OFAC sanctions monitoring | Rare event trigger. SDN list metadata monitoring. Could escalate to FLASH alert. |
| LLM-powered alert evaluation | PydanticAI agent for natural-language alert text generation. Enhancement over rule-based. |
| Email alert delivery | Extend AlertService with SMTP channel. |
| Discord/Telegram bot delivery | Extend AlertService with bot-based delivery channels. |

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/telegram_osint.py` | **Create** |
| `src/options_arena/models/intelligence.py` | Modify — add OsintPost, OsintSnapshot, osint field |
| `src/options_arena/models/config.py` | Modify — add TelegramOsintConfig |
| `src/options_arena/services/intelligence_collector.py` | Modify — wire telegram service |
| `tests/unit/services/test_telegram_osint.py` | **Create** |
