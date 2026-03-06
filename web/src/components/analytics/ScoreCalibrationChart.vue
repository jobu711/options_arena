<script setup lang="ts">
import { computed } from 'vue'
import Select from 'primevue/select'
import type { ScoreCalibrationBucket } from '@/types'

interface Props {
  data: ScoreCalibrationBucket[]
  bucketSize: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:bucketSize': [size: number] }>()

const bucketOptions = [
  { label: '5', value: 5 },
  { label: '10', value: 10 },
  { label: '20', value: 20 },
]

const chartWidth = 560
const chartHeight = 260
const pad = { top: 25, right: 50, bottom: 55, left: 55 }

const maxReturn = computed(() => {
  if (props.data.length === 0) return 10
  const vals = props.data.map(d => Math.abs(d.avg_return_pct))
  return Math.max(Math.ceil(Math.max(...vals) / 5) * 5, 5)
})

const bars = computed(() => {
  if (props.data.length === 0) return []
  const areaW = chartWidth - pad.left - pad.right
  const areaH = chartHeight - pad.top - pad.bottom
  const barW = Math.max(areaW / props.data.length - 4, 8)
  const zeroY = pad.top + areaH / 2

  return props.data.map((d, i) => {
    const x = pad.left + (areaW / props.data.length) * i + (areaW / props.data.length - barW) / 2
    const barH = (Math.abs(d.avg_return_pct) / maxReturn.value) * (areaH / 2)
    const y = d.avg_return_pct >= 0 ? zeroY - barH : zeroY
    const fill = d.avg_return_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'
    return {
      x,
      y,
      width: barW,
      height: Math.max(barH, 1),
      fill,
      label: `${d.score_min.toFixed(0)}-${d.score_max.toFixed(0)}`,
      labelX: x + barW / 2,
      count: d.contract_count,
    }
  })
})

const linePoints = computed(() => {
  if (props.data.length === 0) return ''
  const areaW = chartWidth - pad.left - pad.right
  const areaH = chartHeight - pad.top - pad.bottom
  return props.data.map((d, i) => {
    const x = pad.left + (areaW / props.data.length) * (i + 0.5)
    const y = pad.top + areaH - d.win_rate * areaH
    return `${x},${y}`
  }).join(' ')
})

const lineCircles = computed(() => {
  if (props.data.length === 0) return []
  const areaW = chartWidth - pad.left - pad.right
  const areaH = chartHeight - pad.top - pad.bottom
  return props.data.map((d, i) => ({
    cx: pad.left + (areaW / props.data.length) * (i + 0.5),
    cy: pad.top + areaH - d.win_rate * areaH,
    rate: `${(d.win_rate * 100).toFixed(0)}%`,
  }))
})

const zeroLineY = computed(() => pad.top + (chartHeight - pad.top - pad.bottom) / 2)
</script>

<template>
  <div class="chart-panel" data-testid="analytics-calibration">
    <div class="panel-header">
      <h3>Score Calibration</h3>
      <Select
        :modelValue="bucketSize"
        :options="bucketOptions"
        optionLabel="label"
        optionValue="value"
        class="bucket-select"
        data-testid="bucket-size-select"
        @update:modelValue="emit('update:bucketSize', $event)"
      />
    </div>
    <div v-if="data.length === 0" class="panel-empty">No calibration data available</div>
    <svg
      v-else
      :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
      class="chart-svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <!-- Zero line -->
      <line
        :x1="pad.left"
        :y1="zeroLineY"
        :x2="chartWidth - pad.right"
        :y2="zeroLineY"
        stroke="var(--p-surface-600, #444)"
        stroke-dasharray="4 2"
      />

      <!-- Bars (avg return) -->
      <rect
        v-for="(bar, i) in bars"
        :key="'bar-' + i"
        :x="bar.x"
        :y="bar.y"
        :width="bar.width"
        :height="bar.height"
        :fill="bar.fill"
        opacity="0.8"
        rx="2"
      />

      <!-- Win rate line -->
      <polyline
        :points="linePoints"
        fill="none"
        stroke="var(--accent-blue)"
        stroke-width="2"
        stroke-linejoin="round"
      />
      <circle
        v-for="(c, i) in lineCircles"
        :key="'dot-' + i"
        :cx="c.cx"
        :cy="c.cy"
        r="3.5"
        fill="var(--accent-blue)"
      />

      <!-- X-axis labels -->
      <text
        v-for="(bar, i) in bars"
        :key="'xlabel-' + i"
        :x="bar.labelX"
        :y="chartHeight - pad.bottom + 16"
        text-anchor="middle"
        class="axis-label"
      >{{ bar.label }}</text>

      <!-- Count labels -->
      <text
        v-for="(bar, i) in bars"
        :key="'count-' + i"
        :x="bar.labelX"
        :y="chartHeight - pad.bottom + 30"
        text-anchor="middle"
        class="count-label"
      >n={{ bar.count }}</text>

      <!-- Y-axis labels (left: return) -->
      <text :x="pad.left - 8" :y="pad.top + 4" text-anchor="end" class="axis-label">+{{ maxReturn }}%</text>
      <text :x="pad.left - 8" :y="zeroLineY + 4" text-anchor="end" class="axis-label">0%</text>
      <text :x="pad.left - 8" :y="chartHeight - pad.bottom + 4" text-anchor="end" class="axis-label">-{{ maxReturn }}%</text>

      <!-- Y-axis labels (right: win rate) -->
      <text :x="chartWidth - pad.right + 8" :y="pad.top + 4" text-anchor="start" class="axis-label-blue">100%</text>
      <text :x="chartWidth - pad.right + 8" :y="zeroLineY + 4" text-anchor="start" class="axis-label-blue">50%</text>
      <text :x="chartWidth - pad.right + 8" :y="chartHeight - pad.bottom + 4" text-anchor="start" class="axis-label-blue">0%</text>
    </svg>
    <div v-if="data.length > 0" class="legend">
      <span class="legend-item"><span class="legend-swatch legend-bar" /> Avg Return</span>
      <span class="legend-item"><span class="legend-swatch legend-line" /> Win Rate</span>
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

.bucket-select {
  width: 70px;
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

.axis-label-blue {
  fill: var(--accent-blue);
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

.legend-bar {
  background: var(--accent-green);
  opacity: 0.8;
}

.legend-line {
  background: var(--accent-blue);
  height: 3px;
  border-radius: 1px;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
