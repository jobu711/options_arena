<script setup lang="ts">
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { FundamentalThesis } from '@/types/debate'

interface Props {
  response: FundamentalThesis
}

defineProps<Props>()
</script>

<template>
  <div class="agent-card" data-testid="agent-card-fundamental">
    <div class="agent-header">
      <span class="agent-icon pi pi-building" />
      <span class="agent-name">Fundamental Analysis</span>
      <ConfidenceBadge :value="response.confidence" data-testid="agent-confidence-fundamental" />
    </div>

    <div class="agent-field">
      <span class="field-label">Direction</span>
      <span class="field-value">{{ response.direction }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Catalyst Impact</span>
      <span class="field-value">{{ response.catalyst_impact }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Earnings Assessment</span>
      <span class="field-value">{{ response.earnings_assessment }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">IV Crush Risk</span>
      <span class="field-value">{{ response.iv_crush_risk }}</span>
    </div>

    <div v-if="response.short_interest_analysis != null" class="agent-field">
      <span class="field-label">Short Interest</span>
      <span class="field-value">{{ response.short_interest_analysis }}</span>
    </div>

    <div v-if="response.dividend_impact != null" class="agent-field">
      <span class="field-label">Dividend Impact</span>
      <span class="field-value">{{ response.dividend_impact }}</span>
    </div>

    <div v-if="response.key_fundamental_factors.length > 0" class="agent-section">
      <h4>Key Fundamental Factors</h4>
      <ul>
        <li v-for="(factor, i) in response.key_fundamental_factors" :key="i">{{ factor }}</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.agent-card {
  --agent-color: #14b8a6;
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
