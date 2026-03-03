<script setup lang="ts">
import { computed } from 'vue'
import type { DimensionalScores } from '@/types'

interface Props {
  scores: DimensionalScores | null | undefined
}

const props = defineProps<Props>()

interface BarEntry {
  key: string
  label: string
  value: number | null
}

const FAMILIES: Array<{ key: keyof DimensionalScores; label: string }> = [
  { key: 'trend', label: 'Trend' },
  { key: 'iv_vol', label: 'IV Vol' },
  { key: 'hv_vol', label: 'HV Vol' },
  { key: 'flow', label: 'Flow' },
  { key: 'microstructure', label: 'Micro' },
  { key: 'fundamental', label: 'Fund' },
  { key: 'regime', label: 'Regime' },
  { key: 'risk', label: 'Risk' },
]

const bars = computed<BarEntry[]>(() => {
  return FAMILIES.map((f) => ({
    key: f.key,
    label: f.label,
    value: props.scores?.[f.key] ?? null,
  }))
})

function barWidth(value: number | null): string {
  if (value === null) return '0%'
  return `${Math.min(100, Math.max(0, value))}%`
}

function barColorClass(value: number | null): string {
  if (value === null) return 'bar-fill--null'
  if (value < 30) return 'bar-fill--low'
  if (value < 60) return 'bar-fill--mid'
  return 'bar-fill--high'
}

function displayValue(value: number | null): string {
  if (value === null) return '--'
  return value.toFixed(0)
}
</script>

<template>
  <div class="dim-scores" data-testid="dimensional-score-bars">
    <div
      v-for="bar in bars"
      :key="bar.key"
      class="bar-row"
    >
      <span class="bar-label">{{ bar.label }}</span>
      <div class="bar-track">
        <div
          class="bar-fill"
          :class="barColorClass(bar.value)"
          :style="{ width: barWidth(bar.value) }"
        />
      </div>
      <span class="bar-value mono" :class="barColorClass(bar.value)">
        {{ displayValue(bar.value) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.dim-scores {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bar-label {
  width: 3.5rem;
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  text-align: right;
  flex-shrink: 0;
}

.bar-track {
  flex: 1;
  height: 0.5rem;
  background: var(--p-surface-700, #333);
  border-radius: 0.25rem;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 0.25rem;
  transition: width 0.3s ease;
}

.bar-value {
  width: 2rem;
  font-size: 0.75rem;
  text-align: right;
  flex-shrink: 0;
}

.bar-fill--high {
  background: var(--accent-emerald, #10b981);
  color: var(--accent-emerald, #10b981);
}

.bar-fill--mid {
  background: var(--accent-amber, #f59e0b);
  color: var(--accent-amber, #f59e0b);
}

.bar-fill--low {
  background: var(--accent-red, #ef4444);
  color: var(--accent-red, #ef4444);
}

.bar-fill--null {
  background: var(--accent-gray, #6b7280);
  color: var(--accent-gray, #6b7280);
}

.mono {
  font-family: var(--font-mono);
}
</style>
