<script setup lang="ts">
import Dialog from 'primevue/dialog'
import type { AgentProgressEntry } from '@/types/debate'

interface Props {
  visible: boolean
  ticker: string
  agents: AgentProgressEntry[]
  error: string | null
}

defineProps<Props>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()

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
</script>

<template>
  <Dialog
    :visible="visible"
    :header="`Debating ${ticker}...`"
    :modal="true"
    :closable="false"
    :style="{ width: '400px' }"
    @update:visible="emit('update:visible', $event)"
  >
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
  </Dialog>
</template>

<style scoped>
.agent-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.agent-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: var(--p-surface-800, #1a1a1a);
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
</style>
