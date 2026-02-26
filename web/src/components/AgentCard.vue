<script setup lang="ts">
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { AgentResponse } from '@/types/debate'

interface Props {
  agentName: string
  response: AgentResponse
  color: string
}

defineProps<Props>()
</script>

<template>
  <div class="agent-card" :style="{ '--agent-color': color }">
    <div class="agent-header">
      <span class="agent-icon pi pi-user" />
      <span class="agent-name">{{ agentName }}</span>
      <ConfidenceBadge :value="response.confidence" />
    </div>

    <p class="agent-argument">{{ response.argument }}</p>

    <div v-if="response.key_points.length > 0" class="agent-section">
      <h4>Key Points</h4>
      <ul>
        <li v-for="(point, i) in response.key_points" :key="i">{{ point }}</li>
      </ul>
    </div>

    <div v-if="response.risks_cited.length > 0" class="agent-section">
      <h4>Risks Cited</h4>
      <ul>
        <li v-for="(risk, i) in response.risks_cited" :key="i">{{ risk }}</li>
      </ul>
    </div>

    <div v-if="response.contracts_referenced.length > 0" class="agent-section">
      <h4>Contracts Referenced</h4>
      <div class="contracts-list">
        <span
          v-for="(c, i) in response.contracts_referenced"
          :key="i"
          class="contract-tag mono"
        >
          {{ c }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-left: 4px solid var(--agent-color);
  border-radius: 0.5rem;
  padding: 1rem;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.agent-icon {
  color: var(--agent-color);
}

.agent-name {
  font-weight: 600;
  font-size: 1rem;
  text-transform: capitalize;
  flex: 1;
}

.agent-argument {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
  line-height: 1.5;
  margin: 0 0 0.75rem 0;
}

.agent-section {
  margin-bottom: 0.5rem;
}

.agent-section h4 {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  margin: 0 0 0.35rem 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.agent-section ul {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
}

.agent-section li {
  margin-bottom: 0.2rem;
}

.contracts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.contract-tag {
  font-size: 0.75rem;
  background: var(--p-surface-700, #333);
  padding: 0.15rem 0.4rem;
  border-radius: 0.2rem;
  color: var(--p-surface-200, #ccc);
}

.mono {
  font-family: var(--font-mono);
}
</style>
