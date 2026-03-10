<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import Button from 'primevue/button'
import InputNumber from 'primevue/inputnumber'
import Chart from 'primevue/chart'
import { useToast } from 'primevue/usetoast'
import { useWeightsStore } from '@/stores/weights'
import type { AgentWeight } from '@/types'

const toast = useToast()
const store = useWeightsStore()

const windowDays = ref(90)

/** Map agent names to themed colors — matches AgentAccuracyHeatmap palette. */
const AGENT_COLORS: Record<string, string> = {
  bull: '#22c55e',
  trend: '#22c55e',
  bear: '#ef4444',
  risk: '#3b82f6',
  volatility: '#a855f7',
  contrarian: '#eab308',
  flow: '#06b6d4',
  fundamental: '#f97316',
}

function agentColor(name: string): string {
  return AGENT_COLORS[name.toLowerCase()] ?? '#888'
}

/** Compute delta (auto - manual) for display. */
function delta(w: AgentWeight): number {
  return w.auto_weight - w.manual_weight
}

/** Format delta with sign and color class. */
function deltaClass(w: AgentWeight): string {
  const d = delta(w)
  if (d > 0.001) return 'val-green'
  if (d < -0.001) return 'val-red'
  return ''
}

async function handleAutoTune(): Promise<void> {
  try {
    await store.triggerAutoTune(windowDays.value)
    // Refresh history after tuning
    await store.fetchWeightHistory()
    toast.add({
      severity: 'success',
      summary: 'Auto-Tune Complete',
      detail: `Weights computed with ${windowDays.value}-day window.`,
      life: 5000,
    })
  } catch (err: unknown) {
    toast.add({
      severity: 'error',
      summary: 'Auto-Tune Failed',
      detail: err instanceof Error ? err.message : 'Failed to compute weights',
      life: 5000,
    })
  }
}

// --- Chart data for weight history ---
const chartData = computed(() => {
  if (store.weightHistory.length === 0) return null

  // Collect all unique agent names across all snapshots
  const agentNames = new Set<string>()
  for (const snap of store.weightHistory) {
    for (const w of snap.weights) {
      agentNames.add(w.agent_name)
    }
  }

  // Snapshots are newest-first from API, reverse for chronological x-axis
  const chronological = [...store.weightHistory].reverse()
  const labels = chronological.map(s => {
    const d = new Date(s.computed_at)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  })

  const datasets = [...agentNames].map(name => ({
    label: name.charAt(0).toUpperCase() + name.slice(1),
    data: chronological.map(snap => {
      const found = snap.weights.find(w => w.agent_name === name)
      return found ? found.auto_weight : null
    }),
    borderColor: agentColor(name),
    backgroundColor: agentColor(name),
    tension: 0.3,
    pointRadius: chronological.length > 20 ? 0 : 3,
    pointHoverRadius: 5,
    borderWidth: 2,
    fill: false,
  }))

  return { labels, datasets }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: true,
      position: 'top' as const,
      labels: {
        color: '#888',
        font: { size: 11 },
        usePointStyle: true,
        pointStyle: 'circle',
      },
    },
    tooltip: {
      callbacks: {
        label: (ctx: { dataset: { label: string }; parsed: { y: number } }) =>
          `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}`,
      },
    },
  },
  scales: {
    x: {
      ticks: {
        color: '#888',
        maxTicksLimit: 10,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: {
      ticks: {
        color: '#888',
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
      min: 0,
    },
  },
}))

onMounted(async () => {
  await Promise.all([store.fetchWeights(), store.fetchWeightHistory()])
})
</script>

<template>
  <div class="weight-tuning-panel" data-testid="weight-tuning-panel">
    <!-- Auto-Tune controls -->
    <div class="tune-controls">
      <div class="tune-input-group">
        <label for="window-days" class="tune-label">Window (days)</label>
        <InputNumber
          id="window-days"
          v-model="windowDays"
          :min="1"
          :max="365"
          :showButtons="true"
          :step="30"
          class="window-input"
          data-testid="window-days-input"
        />
      </div>
      <Button
        label="Auto-Tune"
        icon="pi pi-cog"
        severity="info"
        size="small"
        :loading="store.tuning"
        data-testid="btn-auto-tune"
        @click="handleAutoTune"
      />
    </div>

    <!-- Loading state -->
    <div v-if="store.loading && store.weights.length === 0" class="panel-loading">
      <i class="pi pi-spinner pi-spin" />
      <span>Loading weights...</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="store.weights.length === 0" class="panel-empty">
      No tuned weights yet. Click Auto-Tune to compute optimal weights from outcome data.
    </div>

    <!-- Weight table -->
    <template v-else>
      <div class="weight-grid">
        <!-- Header -->
        <div class="grid-header">Agent</div>
        <div class="grid-header">Manual</div>
        <div class="grid-header">Tuned</div>
        <div class="grid-header">Delta</div>
        <div class="grid-header">Brier</div>
        <div class="grid-header">Samples</div>

        <!-- Rows -->
        <template v-for="w in store.weights" :key="w.agent_name">
          <div class="grid-agent">
            <span class="agent-dot" :style="{ background: agentColor(w.agent_name) }" />
            <span class="agent-name">{{ w.agent_name }}</span>
          </div>
          <div class="grid-cell mono">{{ w.manual_weight.toFixed(3) }}</div>
          <div class="grid-cell mono">{{ w.auto_weight.toFixed(3) }}</div>
          <div class="grid-cell mono" :class="deltaClass(w)">
            {{ delta(w) >= 0 ? '+' : '' }}{{ delta(w).toFixed(3) }}
          </div>
          <div class="grid-cell mono">
            {{ w.brier_score !== null ? w.brier_score.toFixed(3) : '--' }}
          </div>
          <div class="grid-cell mono">{{ w.sample_size }}</div>
        </template>
      </div>

      <!-- Weight history chart -->
      <div class="history-section">
        <h3>Weight History</h3>
        <div v-if="!chartData" class="panel-empty">
          No weight history available yet.
        </div>
        <div v-else class="chart-container">
          <Chart type="line" :data="chartData" :options="chartOptions" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.weight-tuning-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.tune-controls {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.tune-input-group {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.tune-label {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.window-input {
  width: 120px;
}

.panel-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--p-surface-400, #888);
  font-size: 0.85rem;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}

.weight-grid {
  display: grid;
  grid-template-columns: 1fr repeat(5, auto);
  gap: 1px;
  font-size: 0.85rem;
}

.grid-header {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-500, #666);
  padding: 0.25rem 0.75rem;
  border-bottom: 1px solid var(--p-surface-700, #333);
}

.grid-agent {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
}

.agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.agent-name {
  text-transform: capitalize;
  color: var(--p-surface-200, #ccc);
}

.grid-cell {
  padding: 0.4rem 0.75rem;
  text-align: right;
  color: var(--p-surface-200, #ccc);
  border-radius: 3px;
}

.mono {
  font-family: var(--font-mono);
}

.val-green {
  color: var(--accent-green);
}

.val-red {
  color: var(--accent-red);
}

.history-section {
  margin-top: 1.5rem;
}

.history-section h3 {
  font-size: 0.95rem;
  margin: 0 0 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.chart-container {
  height: 280px;
}

@media (max-width: 768px) {
  .tune-controls {
    flex-direction: column;
    align-items: stretch;
  }

  .weight-grid {
    font-size: 0.75rem;
    grid-template-columns: 1fr repeat(5, auto);
  }

  .grid-cell,
  .grid-agent,
  .grid-header {
    padding: 0.3rem 0.5rem;
  }
}
</style>
