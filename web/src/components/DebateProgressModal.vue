<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import DirectionBadge from './DirectionBadge.vue'
import ConfidenceBadge from './ConfidenceBadge.vue'
import type { AgentProgressEntry } from '@/types/debate'
import type { BatchTickerProgress } from '@/stores/debate'
import type { BatchTickerResultEvent } from '@/types/ws'

interface Props {
  visible: boolean
  // Single debate mode
  ticker?: string
  agents?: AgentProgressEntry[]
  error?: string | null
  // Batch mode
  batchMode?: boolean
  batchTickers?: BatchTickerProgress[]
  batchResults?: BatchTickerResultEvent[]
  batchComplete?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  ticker: '',
  agents: () => [],
  error: null,
  batchMode: false,
  batchTickers: () => [],
  batchResults: () => [],
  batchComplete: false,
})

const emit = defineEmits<{ 'update:visible': [value: boolean] }>()
const router = useRouter()

const headerText = computed(() => {
  if (!props.batchMode) return `Debating ${props.ticker}...`
  const completedCount = props.batchTickers.filter(
    (t) => t.status === 'completed' || t.status === 'failed',
  ).length
  const total = props.batchTickers.length
  if (props.batchComplete) return `Batch Complete (${total} tickers)`
  return `Batch Debate ${completedCount}/${total}`
})

const currentBatchTicker = computed(
  () => props.batchTickers.find((t) => t.status === 'started') ?? null,
)

function statusIcon(status: string): string {
  switch (status) {
    case 'completed':
      return 'pi pi-check-circle'
    case 'started':
      return 'pi pi-spin pi-spinner'
    case 'failed':
      return 'pi pi-times-circle'
    default:
      return 'pi pi-circle'
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'status--completed'
    case 'started':
      return 'status--started'
    case 'failed':
      return 'status--failed'
    default:
      return 'status--pending'
  }
}

const AGENT_LABELS: Record<string, string> = {
  bull: 'Bull Agent',
  bear: 'Bear Agent',
  risk: 'Risk Agent',
  rebuttal: 'Bull Rebuttal',
  volatility: 'Volatility Agent',
}

function navigateToDebate(debateId: number): void {
  emit('update:visible', false)
  void router.push(`/debate/${debateId}`)
}

function closeBatch(): void {
  emit('update:visible', false)
}
</script>

<template>
  <Dialog
    :visible="visible"
    :header="headerText"
    :modal="true"
    :closable="batchComplete"
    :style="{ width: '520px', maxWidth: '95vw', transition: 'width 0.2s ease' }"
    :data-testid="batchMode ? 'batch-progress-modal' : 'debate-progress-modal'"
    @update:visible="emit('update:visible', $event)"
  >
    <!-- SINGLE DEBATE MODE -->
    <template v-if="!batchMode">
      <div class="agent-list">
        <div
          v-for="agent in agents"
          :key="agent.name"
          class="agent-row"
          :class="statusClass(agent.status)"
        >
          <span :class="statusIcon(agent.status)" class="agent-status-icon" />
          <span class="agent-label">{{ AGENT_LABELS[agent.name] ?? agent.name }}</span>
          <span v-if="agent.confidence !== null" class="agent-confidence mono">
            {{ (agent.confidence * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
      <p v-if="error" class="error-msg">{{ error }}</p>
    </template>

    <!-- BATCH MODE -->
    <template v-else>
      <!-- Overall progress bar -->
      <div class="batch-progress-bar">
        <div class="batch-bar-track">
          <div
            class="batch-bar-fill"
            :style="{
              width:
                (batchTickers.filter((t) => t.status === 'completed' || t.status === 'failed')
                  .length /
                  Math.max(batchTickers.length, 1)) *
                  100 +
                '%',
            }"
          />
        </div>
      </div>

      <!-- Current ticker agents -->
      <div v-if="currentBatchTicker && !batchComplete" class="current-ticker-section">
        <div class="current-ticker-header">
          <span class="pi pi-spin pi-spinner current-spinner" />
          <span class="current-label">{{ currentBatchTicker.ticker }}</span>
        </div>
        <div class="agent-list compact">
          <div
            v-for="agent in currentBatchTicker.agents"
            :key="agent.name"
            class="agent-row compact"
            :class="statusClass(agent.status)"
          >
            <span :class="statusIcon(agent.status)" class="agent-status-icon" />
            <span class="agent-label">{{ AGENT_LABELS[agent.name] ?? agent.name }}</span>
            <span v-if="agent.confidence !== null" class="agent-confidence mono">
              {{ (agent.confidence * 100).toFixed(0) }}%
            </span>
          </div>
        </div>
      </div>

      <!-- Ticker results list -->
      <div class="batch-ticker-list">
        <div
          v-for="entry in batchTickers"
          :key="entry.ticker"
          class="batch-ticker-row"
          :class="statusClass(entry.status)"
        >
          <span :class="statusIcon(entry.status)" class="agent-status-icon" />
          <span class="ticker-name mono">{{ entry.ticker }}</span>
          <template v-if="entry.result && !entry.result.error">
            <DirectionBadge
              v-if="entry.result.direction"
              :direction="entry.result.direction as 'bullish' | 'bearish' | 'neutral'"
            />
            <ConfidenceBadge v-if="entry.result.confidence !== null" :value="entry.result.confidence" />
            <Button
              v-if="entry.result.debate_id !== null"
              icon="pi pi-external-link"
              size="small"
              text
              rounded
              class="result-link"
              @click="navigateToDebate(entry.result.debate_id!)"
            />
          </template>
          <span v-else-if="entry.result?.error" class="ticker-error">{{ entry.result.error }}</span>
        </div>
      </div>

      <!-- Batch error -->
      <p v-if="error" class="error-msg">{{ error }}</p>

      <!-- Close button when complete -->
      <div v-if="batchComplete" class="batch-footer">
        <Button label="Close" severity="secondary" size="small" @click="closeBatch()" />
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.agent-list.compact {
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.agent-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: var(--p-surface-800, #1a1a1a);
}

.agent-row.compact {
  padding: 0.3rem 0.5rem;
  font-size: 0.85rem;
}

.agent-status-icon {
  font-size: 1rem;
  width: 1.25rem;
  text-align: center;
}

.status--completed .agent-status-icon {
  color: var(--accent-green);
}

.status--started .agent-status-icon {
  color: var(--accent-blue);
}

.status--failed .agent-status-icon {
  color: var(--accent-red);
}

.status--pending .agent-status-icon {
  color: var(--p-surface-500, #666);
}

.agent-label {
  flex: 1;
  font-size: 0.9rem;
}

.agent-confidence {
  font-size: 0.8rem;
  color: var(--p-surface-300, #aaa);
}

.mono {
  font-family: var(--font-mono);
}

.error-msg {
  margin-top: 0.75rem;
  color: var(--accent-red);
  font-size: 0.85rem;
}

/* Batch mode styles */
.batch-progress-bar {
  margin-bottom: 1rem;
}

.batch-bar-track {
  height: 6px;
  background: var(--p-surface-700, #333);
  border-radius: 3px;
  overflow: hidden;
}

.batch-bar-fill {
  height: 100%;
  background: var(--accent-blue);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.current-ticker-section {
  margin-bottom: 0.75rem;
}

.current-ticker-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}

.current-spinner {
  color: var(--accent-blue);
  font-size: 0.9rem;
}

.current-label {
  font-weight: 600;
  font-size: 0.9rem;
}

.batch-ticker-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.batch-ticker-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border-radius: 0.375rem;
  background: var(--p-surface-800, #1a1a1a);
}

.ticker-name {
  font-weight: 600;
  font-size: 0.85rem;
  min-width: 50px;
}

.ticker-error {
  font-size: 0.8rem;
  color: var(--accent-red);
}

.result-link {
  margin-left: auto;
}

.batch-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}
</style>
