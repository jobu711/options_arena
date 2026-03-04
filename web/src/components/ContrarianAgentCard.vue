<script setup lang="ts">
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { ContrarianThesis } from '@/types/debate'

interface Props {
  response: ContrarianThesis
}

defineProps<Props>()
</script>

<template>
  <div class="agent-card" data-testid="agent-card-contrarian">
    <div class="agent-header">
      <span class="agent-icon pi pi-exclamation-triangle" />
      <span class="agent-name">Contrarian Challenge</span>
      <ConfidenceBadge :value="response.dissent_confidence" data-testid="agent-confidence-contrarian" />
    </div>

    <div class="agent-field">
      <span class="field-label">Dissent Direction</span>
      <span class="field-value">{{ response.dissent_direction }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Primary Challenge</span>
      <span class="field-value">{{ response.primary_challenge }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Consensus Weakness</span>
      <span class="field-value">{{ response.consensus_weakness }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Alternative Scenario</span>
      <span class="field-value">{{ response.alternative_scenario }}</span>
    </div>

    <div v-if="response.overlooked_risks.length > 0" class="agent-section">
      <h4>Overlooked Risks</h4>
      <ul>
        <li v-for="(risk, i) in response.overlooked_risks" :key="i">{{ risk }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.agent-card {
  --agent-color: #eab308;
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
  flex: 1;
}

.agent-field {
  margin-bottom: 0.5rem;
}

.field-label {
  display: block;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
  margin-bottom: 0.1rem;
}

.field-value {
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
  line-height: 1.4;
}

.agent-section {
  margin-top: 0.5rem;
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
</style>
