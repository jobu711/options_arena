# Analysis: #255 — Frontend V2 Types, Cards, Protocol-Aware Page

## Key Files to Create
| File | Purpose |
|------|---------|
| `web/src/components/FlowAgentCard.vue` | Flow agent card (orange #f97316) |
| `web/src/components/FundamentalAgentCard.vue` | Fundamental agent card (teal #14b8a6) |
| `web/src/components/RiskAgentCard.vue` | Risk agent card (blue #3b82f6) |
| `web/src/components/ContrarianAgentCard.vue` | Contrarian agent card (yellow #eab308) |

## Key Files to Modify
| File | What to change |
|------|---------------|
| `web/src/types/debate.ts` | 4 new interfaces + 5 fields on DebateResult |
| `web/src/types/ws.ts` | Extend DebateAgentEvent.name union with v2 agent names |
| `web/src/pages/DebateResultPage.vue` | Protocol detection + v2 6-card grid |
| `web/src/stores/debate.ts` | V2 agent progress initialization |

## API Shape (from #254)
DebateResultDetail now returns:
- flow_response: dict | null
- fundamental_response: dict | null
- risk_v2_response: dict | null
- contrarian_response: dict | null
- debate_protocol: string | null

## Card Styling Pattern
- Follow existing AgentCard.vue: `<script setup lang="ts">`, `defineProps<Props>()`
- Scoped CSS: `border-left: 4px solid var(--agent-color)`
- Background: `var(--p-surface-800)`
- Use existing ConfidenceBadge and DirectionBadge components if available
