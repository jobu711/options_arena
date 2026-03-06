<script setup lang="ts">
import { computed } from 'vue'
import Select from 'primevue/select'
import type { DeltaPerformanceResult } from '@/types'

interface Props {
  data: DeltaPerformanceResult[]
  holdingDays: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:holdingDays': [days: number] }>()

const holdingOptions = [
  { label: '1 day', value: 1 },
  { label: '5 days', value: 5 },
  { label: '10 days', value: 10 },
  { label: '20 days', value: 20 },
]

const chartWidth = 560
const chartHeight = 260
const pad = { top: 25, right: 20, bottom: 55, left: 50 }

const maxVal = computed(() => {
  if (props.data.length === 0) return 10
  const returns = props.data.map(d => Math.abs(d.avg_return_pct))
  const rates = props.data.map(d => d.win_rate * 100)
  return Math.max(Math.ceil(Math.max(...returns, ...rates) / 10) * 10, 10)
})

const groups = computed(() => {
  if (props.data.length === 0) return []
  const areaW = chartWidth - pad.left - pad.right
  const areaH = chartHeight - pad.top - pad.bottom
  const groupW = areaW / props.data.length
  const barW = Math.max((groupW - 8) / 2 - 2, 6)

  return props.data.map((d, i) => {
    const groupX = pad.left + groupW * i
    const returnH = (Math.abs(d.avg_return_pct) / maxVal.value) * areaH
    const returnY = d.avg_return_pct >= 0
      ? pad.top + areaH - returnH
      : pad.top + areaH
    const winH = (d.win_rate * 100 / maxVal.value) * areaH
    const winY = pad.top + areaH - winH

    return {
      returnBar: {
        x: groupX + (groupW / 2 - barW - 1),
        y: d.avg_return_pct >= 0 ? returnY : returnY,
        width: barW,
        height: Math.max(returnH, 1),
        fill: d.avg_return_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)',
      },
      winBar: {
        x: groupX + (groupW / 2 + 1),
        y: winY,
        width: barW,
        height: Math.max(winH, 1),
        fill: 'var(--accent-blue)',
      },
      label: `${d.delta_min.toFixed(1)}-${d.delta_max.toFixed(1)}`,
      labelX: groupX + groupW / 2,
      samples: `n=${d.sample_size}`,
    }
  })
})
</script>

<template>
  <div class="chart-panel" data-testid="analytics-delta">
    <div class="panel-header">
      <h3>Delta Performance</h3>
      <Select
        :modelValue="holdingDays"
        :options="holdingOptions"
        optionLabel="label"
        optionValue="value"
        class="holding-select"
        data-testid="holding-days-select"
        @update:modelValue="emit('update:holdingDays', $event)"
      />
    </div>
    <div v-if="data.length === 0" class="panel-empty">No delta performance data available</div>
    <svg
      v-else
      :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
      class="chart-svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <!-- Grouped bars -->
      <template v-for="(g, i) in groups" :key="i">
        <rect
          :x="g.returnBar.x"
          :y="g.returnBar.y"
          :width="g.returnBar.width"
          :height="g.returnBar.height"
          :fill="g.returnBar.fill"
          opacity="0.85"
          rx="2"
        />
        <rect
          :x="g.winBar.x"
          :y="g.winBar.y"
          :width="g.winBar.width"
          :height="g.winBar.height"
          :fill="g.winBar.fill"
          opacity="0.7"
          rx="2"
        />
      </template>

      <!-- X-axis labels -->
      <text
        v-for="(g, i) in groups"
        :key="'xlabel-' + i"
        :x="g.labelX"
        :y="chartHeight - pad.bottom + 16"
        text-anchor="middle"
        class="axis-label"
      >{{ g.label }}</text>
      <text
        v-for="(g, i) in groups"
        :key="'xsamp-' + i"
        :x="g.labelX"
        :y="chartHeight - pad.bottom + 30"
        text-anchor="middle"
        class="count-label"
      >{{ g.samples }}</text>

      <!-- Y-axis labels -->
      <text :x="pad.left - 8" :y="pad.top + 4" text-anchor="end" class="axis-label">{{ maxVal }}%</text>
      <text :x="pad.left - 8" :y="pad.top + (chartHeight - pad.top - pad.bottom) / 2 + 4" text-anchor="end" class="axis-label">{{ (maxVal / 2).toFixed(0) }}%</text>
      <text :x="pad.left - 8" :y="chartHeight - pad.bottom + 4" text-anchor="end" class="axis-label">0%</text>
    </svg>
    <div v-if="data.length > 0" class="legend">
      <span class="legend-item"><span class="legend-swatch legend-return" /> Avg Return</span>
      <span class="legend-item"><span class="legend-swatch legend-win" /> Win Rate</span>
    </div>
  </div>
</template>

<style scoped>
.chart-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.panel-header h3 {
  font-size: 0.95rem;
  margin: 0;
  color: var(--p-surface-200, #ccc);
}

.holding-select {
  width: 110px;
}

.chart-svg {
  width: 100%;
  height: auto;
}

.axis-label {
  fill: var(--p-surface-400, #888);
  font-size: 10px;
  font-family: var(--font-mono);
}

.count-label {
  fill: var(--p-surface-500, #666);
  font-size: 9px;
  font-family: var(--font-mono);
}

.legend {
  display: flex;
  gap: 1.5rem;
  justify-content: center;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.legend-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.legend-return {
  background: var(--accent-green);
  opacity: 0.85;
}

.legend-win {
  background: var(--accent-blue);
  opacity: 0.7;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
