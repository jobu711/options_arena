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

function tierClass(value: number | null): string {
  if (value === null) return 'tier--null'
  if (value < 30) return 'tier--low'
  if (value < 60) return 'tier--mid'
  return 'tier--high'
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
      :class="tierClass(bar.value)"
    >
      <span class="bar-label">{{ bar.label }}</span>
      <div class="bar-track">
        <div
          class="bar-fill"
          :style="{ width: barWidth(bar.value) }"
        />
      </div>
      <span class="bar-value mono">
        {{ displayValue(bar.value) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.dim-scores {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bar-label {
  width: 3.5rem;
  font-size: 0.75rem;
  color: var(--p-surface-300, #aaa);
  text-align: right;
  flex-shrink: 0;
}

.bar-track {
  flex: 1;
  height: 0.5rem;
  background: var(--p-surface-700, #333);
  border-radius: 0.25rem;
  overflow: hidden;
  min-width: 0;
}

.bar-fill {
  height: 100%;
  border-radius: 0.25rem;
  transition: width 0.3s ease;
}

.bar-value {
  width: 2.25rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-align: right;
  flex-shrink: 0;
}

/* --- Tier colors: bar fill via .bar-fill, text via .bar-value --- */
.tier--high .bar-fill {
  background: var(--accent-emerald, #10b981);
}
.tier--high .bar-value {
  color: var(--accent-emerald, #10b981);
}

.tier--mid .bar-fill {
  background: var(--accent-amber, #f59e0b);
}
.tier--mid .bar-value {
  color: var(--accent-amber, #f59e0b);
}

.tier--low .bar-fill {
  background: var(--accent-red, #ef4444);
}
.tier--low .bar-value {
  color: var(--accent-red, #ef4444);
}

.tier--null .bar-fill {
  background: var(--p-surface-600, #555);
}
.tier--null .bar-value {
  color: var(--p-surface-400, #888);
}

.mono {
  font-family: var(--font-mono);
}
</style>
