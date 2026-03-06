<script setup lang="ts">
import Tag from 'primevue/tag'
import type { PerformanceSummary } from '@/types'

interface Props {
  summary: PerformanceSummary | null
  lookbackDays: number
}

defineProps<Props>()
defineEmits<{ 'update:lookbackDays': [days: number] }>()

function formatPct(val: number | null): string {
  if (val == null) return '--'
  return `${(val * 100).toFixed(1)}%`
}

function formatReturnPct(val: number | null): string {
  if (val == null) return '--'
  const prefix = val >= 0 ? '+' : ''
  return `${prefix}${val.toFixed(1)}%`
}

function directionSeverity(dir: string): 'success' | 'danger' | 'warn' {
  if (dir === 'bullish') return 'success'
  if (dir === 'bearish') return 'danger'
  return 'warn'
}
</script>

<template>
  <section v-if="summary" class="summary-section" data-testid="analytics-summary">
    <h2>Performance Summary (Last {{ summary.lookback_days }} days)</h2>
    <div class="summary-grid">
      <div class="summary-card">
        <span class="summary-value mono">{{ summary.total_contracts.toLocaleString() }}</span>
        <span class="summary-label">Total Contracts</span>
      </div>
      <div class="summary-card">
        <span class="summary-value mono">{{ summary.total_with_outcomes.toLocaleString() }}</span>
        <span class="summary-label">With Outcomes</span>
      </div>
      <div class="summary-card">
        <span
          class="summary-value mono"
          :class="{ 'val-green': (summary.overall_win_rate ?? 0) > 0.5 }"
        >{{ formatPct(summary.overall_win_rate) }}</span>
        <span class="summary-label">Win Rate</span>
      </div>
      <div class="summary-card">
        <span
          class="summary-value mono"
          :class="summary.avg_stock_return_pct != null && summary.avg_stock_return_pct >= 0 ? 'val-green' : 'val-red'"
        >{{ formatReturnPct(summary.avg_stock_return_pct) }}</span>
        <span class="summary-label">Avg Stock Return</span>
      </div>
      <div class="summary-card">
        <span
          class="summary-value mono"
          :class="summary.avg_contract_return_pct != null && summary.avg_contract_return_pct >= 0 ? 'val-green' : 'val-red'"
        >{{ formatReturnPct(summary.avg_contract_return_pct) }}</span>
        <span class="summary-label">Avg Contract Return</span>
      </div>
      <div v-if="summary.best_direction" class="summary-card">
        <Tag :value="summary.best_direction" :severity="directionSeverity(summary.best_direction)" />
        <span class="summary-label">Best Direction</span>
      </div>
      <div v-if="summary.best_holding_days != null" class="summary-card">
        <span class="summary-value mono">{{ summary.best_holding_days }}d</span>
        <span class="summary-label">Best Holding Period</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.summary-section {
  margin-bottom: 1.5rem;
}

.summary-section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.summary-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.summary-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem 1.5rem;
  min-width: 120px;
}

.summary-value {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--p-surface-100, #eee);
}

.summary-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-surface-500, #666);
}

.val-green { color: var(--accent-green); }
.val-red { color: var(--accent-red); }

.mono { font-family: var(--font-mono); }
</style>
