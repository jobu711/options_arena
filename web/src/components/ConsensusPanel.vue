<script setup lang="ts">
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'

interface Props {
  agreementScore: number | null
  agentsCompleted: number | null
  dissentingAgents: string[]
  contrarianDissent: string | null
}

const props = defineProps<Props>()

/** Agreement score as a 0-100 integer for the progress bar. */
function agreementPercent(): number {
  if (props.agreementScore == null) return 0
  return Math.round(props.agreementScore * 100)
}

/** Color class based on agreement level. */
function agreementSeverity(): string {
  const pct = agreementPercent()
  if (pct >= 75) return 'high-agreement'
  if (pct >= 50) return 'mid-agreement'
  return 'low-agreement'
}
</script>

<template>
  <div class="consensus-panel" data-testid="consensus-panel">
    <h3 class="panel-header">Consensus</h3>

    <div class="panel-body">
      <!-- Agreement Score -->
      <div class="agreement-section">
        <div class="agreement-header">
          <span class="section-label">Agreement</span>
          <span class="agreement-value mono" :class="agreementSeverity()">
            {{ agreementPercent() }}%
          </span>
        </div>
        <ProgressBar
          :value="agreementPercent()"
          :showValue="false"
          class="agreement-bar"
          :class="agreementSeverity()"
        />
      </div>

      <!-- Agents Completed -->
      <div v-if="props.agentsCompleted != null" class="participation-section">
        <span class="section-label">Participation</span>
        <span class="participation-value mono">
          {{ props.agentsCompleted }}/8 agents participated
        </span>
      </div>

      <!-- Dissenting Agents -->
      <div v-if="props.dissentingAgents.length > 0" class="dissent-section">
        <span class="section-label">Dissenting Agents</span>
        <div class="dissent-tags">
          <Tag
            v-for="agent in props.dissentingAgents"
            :key="agent"
            :value="agent"
            severity="warn"
            class="dissent-tag"
          />
        </div>
      </div>

      <!-- Contrarian Challenge -->
      <div v-if="props.contrarianDissent" class="contrarian-section">
        <span class="section-label">Contrarian Challenge</span>
        <blockquote class="contrarian-quote">
          {{ props.contrarianDissent }}
        </blockquote>
      </div>
    </div>
  </div>
</template>

<style scoped>
.consensus-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
}

.panel-header {
  color: var(--p-text-muted-color, var(--p-surface-400, #888));
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 0.75rem 0;
  font-weight: 600;
}

.panel-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-400, #888);
}

.mono {
  font-family: var(--font-mono);
}

/* Agreement Score */
.agreement-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.agreement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.agreement-value {
  font-size: 1.1rem;
  font-weight: 600;
}

.agreement-value.high-agreement {
  color: var(--accent-green, #22c55e);
}

.agreement-value.mid-agreement {
  color: var(--accent-yellow, #eab308);
}

.agreement-value.low-agreement {
  color: var(--accent-red, #ef4444);
}

.agreement-bar {
  height: 0.5rem;
  border-radius: 0.25rem;
}

.agreement-bar.high-agreement :deep(.p-progressbar-value) {
  background: var(--accent-green, #22c55e);
}

.agreement-bar.mid-agreement :deep(.p-progressbar-value) {
  background: var(--accent-yellow, #eab308);
}

.agreement-bar.low-agreement :deep(.p-progressbar-value) {
  background: var(--accent-red, #ef4444);
}

/* Participation */
.participation-section {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.participation-value {
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
}

/* Dissenting Agents */
.dissent-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.dissent-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.dissent-tag {
  text-transform: capitalize;
}

/* Contrarian Challenge */
.contrarian-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.contrarian-quote {
  margin: 0;
  padding: 0.75rem 1rem;
  border-left: 3px solid var(--accent-purple, #a855f7);
  background: var(--p-surface-900, #111);
  border-radius: 0 0.25rem 0.25rem 0;
  font-size: 0.85rem;
  color: var(--p-surface-200, #ccc);
  line-height: 1.5;
  font-style: italic;
}
</style>
