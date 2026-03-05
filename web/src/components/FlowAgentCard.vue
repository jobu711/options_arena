<script setup lang="ts">
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { FlowThesis } from '@/types/debate'

interface Props {
  response: FlowThesis
}

defineProps<Props>()
</script>

<template>
  <div class="agent-card" data-testid="agent-card-flow">
    <div class="agent-header">
      <span class="agent-icon pi pi-chart-bar" />
      <span class="agent-name">Flow Analysis</span>
      <ConfidenceBadge :value="response.confidence" data-testid="agent-confidence-flow" />
    </div>

    <div class="agent-field">
      <span class="field-label">Direction</span>
      <span class="field-value">{{ response.direction }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">GEX Interpretation</span>
      <span class="field-value">{{ response.gex_interpretation }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Smart Money Signal</span>
      <span class="field-value">{{ response.smart_money_signal }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">OI Analysis</span>
      <span class="field-value">{{ response.oi_analysis }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Volume Confirmation</span>
      <span class="field-value">{{ response.volume_confirmation }}</span>
    </div>

    <div v-if="response.key_flow_factors.length > 0" class="agent-section">
      <h4>Key Flow Factors</h4>
      <ul>
        <li v-for="(factor, i) in response.key_flow_factors" :key="i">{{ factor }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.agent-card {
  --agent-color: #f97316;
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
  color: var(--p-surface-300, #aaa);
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
  color: var(--p-surface-300, #aaa);
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
