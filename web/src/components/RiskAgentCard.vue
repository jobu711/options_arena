<script setup lang="ts">
import { computed } from 'vue'
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { RiskAssessmentThesis } from '@/types/debate'

interface Props {
  response: RiskAssessmentThesis
}

const props = defineProps<Props>()

const popDisplay = computed(() => {
  if (props.response.pop_estimate == null) return null
  return `${(props.response.pop_estimate * 100).toFixed(0)}%`
})
</script>

<template>
  <div class="agent-card" data-testid="agent-card-risk">
    <div class="agent-header">
      <span class="agent-icon pi pi-shield" />
      <span class="agent-name">Risk Assessment</span>
      <ConfidenceBadge :value="response.confidence" data-testid="agent-confidence-risk" />
    </div>

    <div class="agent-field">
      <span class="field-label">Risk Level</span>
      <span class="field-value risk-level">{{ response.risk_level }}</span>
    </div>

    <div v-if="popDisplay != null" class="agent-field">
      <span class="field-label">Probability of Profit</span>
      <span class="field-value mono">{{ popDisplay }}</span>
    </div>

    <div class="agent-field">
      <span class="field-label">Max Loss Estimate</span>
      <span class="field-value">{{ response.max_loss_estimate }}</span>
    </div>

    <div v-if="response.charm_decay_warning != null" class="agent-field">
      <span class="field-label">Charm Decay Warning</span>
      <span class="field-value">{{ response.charm_decay_warning }}</span>
    </div>

    <div v-if="response.spread_quality_assessment != null" class="agent-field">
      <span class="field-label">Spread Quality</span>
      <span class="field-value">{{ response.spread_quality_assessment }}</span>
    </div>

    <div v-if="response.key_risks.length > 0" class="agent-section">
      <h4>Key Risks</h4>
      <ul>
        <li v-for="(risk, i) in response.key_risks" :key="i">{{ risk }}</li>
      </ul>
    </div>

    <div v-if="response.risk_mitigants.length > 0" class="agent-section">
      <h4>Risk Mitigants</h4>
      <ul>
        <li v-for="(mitigant, i) in response.risk_mitigants" :key="i">{{ mitigant }}</li>
      </ul>
    </div>

    <div v-if="response.recommended_position_size != null" class="agent-field">
      <span class="field-label">Recommended Position Size</span>
      <span class="field-value">{{ response.recommended_position_size }}</span>
    </div>
  </div>
</template>

<style scoped>
.agent-card {
  --agent-color: #3b82f6;
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

.risk-level {
  text-transform: capitalize;
  font-weight: 600;
}

.mono {
  font-family: var(--font-mono);
}

.agent-section {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
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
