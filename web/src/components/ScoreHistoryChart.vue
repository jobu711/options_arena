<script setup lang="ts">
import { computed, ref } from 'vue'
import type { HistoryPoint } from '@/types'

interface Props {
  history: HistoryPoint[]
}

const props = defineProps<Props>()

const WIDTH = 600
const HEIGHT = 200
const PADDING_TOP = 20
const PADDING_BOTTOM = 40
const PADDING_LEFT = 40
const PADDING_RIGHT = 20

const chartWidth = WIDTH - PADDING_LEFT - PADDING_RIGHT
const chartHeight = HEIGHT - PADDING_TOP - PADDING_BOTTOM

const hoveredIndex = ref<number | null>(null)

function directionColor(direction: string): string {
  switch (direction) {
    case 'bullish':
      return 'var(--accent-green, #22c55e)'
    case 'bearish':
      return 'var(--accent-red, #ef4444)'
    default:
      return 'var(--accent-yellow, #eab308)'
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

interface ChartPoint {
  x: number
  y: number
  score: number
  date: string
  direction: string
  label: string
}

const points = computed<ChartPoint[]>(() => {
  const data = props.history
  if (data.length === 0) return []

  const count = data.length
  return data.map((pt, i) => {
    const x = PADDING_LEFT + (count > 1 ? (i / (count - 1)) * chartWidth : chartWidth / 2)
    const y = PADDING_TOP + chartHeight - (pt.composite_score / 100) * chartHeight
    return {
      x,
      y,
      score: pt.composite_score,
      date: pt.scan_date,
      direction: pt.direction,
      label: `${formatDate(pt.scan_date)}: ${pt.composite_score.toFixed(1)} (${pt.direction})`,
    }
  })
})

const polylinePoints = computed<string>(() => {
  return points.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
})

// Y-axis ticks: 0, 25, 50, 75, 100
const yTicks = [0, 25, 50, 75, 100]

function yTickY(value: number): number {
  return PADDING_TOP + chartHeight - (value / 100) * chartHeight
}

// X-axis labels: show up to ~6 evenly spaced dates
const xLabels = computed(() => {
  const data = props.history
  if (data.length === 0) return []
  const maxLabels = Math.min(6, data.length)
  const step = Math.max(1, Math.floor((data.length - 1) / (maxLabels - 1)))
  const labels: Array<{ x: number; text: string }> = []
  for (let i = 0; i < data.length; i += step) {
    const pt = points.value[i]
    if (pt) {
      labels.push({ x: pt.x, text: formatDate(data[i].scan_date) })
    }
  }
  // Always include the last point
  const lastPt = points.value[points.value.length - 1]
  if (lastPt && (labels.length === 0 || labels[labels.length - 1].x !== lastPt.x)) {
    labels.push({ x: lastPt.x, text: formatDate(data[data.length - 1].scan_date) })
  }
  return labels
})

const tooltipStyle = computed(() => {
  if (hoveredIndex.value === null) return { display: 'none' }
  const pt = points.value[hoveredIndex.value]
  if (!pt) return { display: 'none' }
  return {
    display: 'block',
    left: `${((pt.x / WIDTH) * 100).toFixed(1)}%`,
    top: `${((pt.y / HEIGHT) * 100 - 12).toFixed(1)}%`,
  }
})

const tooltipText = computed<string>(() => {
  if (hoveredIndex.value === null) return ''
  const pt = points.value[hoveredIndex.value]
  return pt ? pt.label : ''
})
</script>

<template>
  <div class="score-history-chart" data-testid="score-history-chart">
    <svg
      v-if="history.length >= 2"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      preserveAspectRatio="xMidYMid meet"
      class="chart-svg"
    >
      <!-- Y-axis grid lines and labels -->
      <g class="y-axis">
        <template v-for="tick in yTicks" :key="tick">
          <line
            :x1="PADDING_LEFT"
            :y1="yTickY(tick)"
            :x2="WIDTH - PADDING_RIGHT"
            :y2="yTickY(tick)"
            class="grid-line"
          />
          <text
            :x="PADDING_LEFT - 6"
            :y="yTickY(tick) + 4"
            class="axis-label"
            text-anchor="end"
          >{{ tick }}</text>
        </template>
      </g>

      <!-- X-axis labels -->
      <g class="x-axis">
        <text
          v-for="(label, i) in xLabels"
          :key="i"
          :x="label.x"
          :y="HEIGHT - 8"
          class="axis-label"
          text-anchor="middle"
        >{{ label.text }}</text>
      </g>

      <!-- Polyline connecting data points -->
      <polyline
        v-if="points.length >= 2"
        :points="polylinePoints"
        fill="none"
        stroke="var(--p-surface-400, #888)"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />

      <!-- Data point circles -->
      <circle
        v-for="(pt, i) in points"
        :key="i"
        :cx="pt.x"
        :cy="pt.y"
        r="4"
        :fill="directionColor(pt.direction)"
        stroke="var(--p-surface-800, #1a1a1a)"
        stroke-width="1.5"
        class="data-point"
        data-testid="chart-point"
        @mouseenter="hoveredIndex = i"
        @mouseleave="hoveredIndex = null"
      >
        <title>{{ pt.label }}</title>
      </circle>
    </svg>

    <!-- Custom tooltip -->
    <div v-if="hoveredIndex !== null" class="chart-tooltip" :style="tooltipStyle">
      {{ tooltipText }}
    </div>

    <div v-if="history.length < 2" class="no-data" data-testid="chart-no-data">
      Not enough data to display chart.
    </div>
  </div>
</template>

<style scoped>
.score-history-chart {
  position: relative;
  width: 100%;
  height: 200px;
}

.chart-svg {
  width: 100%;
  height: 100%;
}

.grid-line {
  stroke: var(--p-surface-700, #333);
  stroke-width: 0.5;
  stroke-dasharray: 4 4;
}

.axis-label {
  fill: var(--p-surface-500, #666);
  font-size: 10px;
  font-family: var(--font-mono);
}

.data-point {
  cursor: pointer;
  transition: r 0.15s;
}

.data-point:hover {
  r: 6;
}

.chart-tooltip {
  position: absolute;
  transform: translateX(-50%);
  background: var(--p-surface-700, #333);
  color: var(--p-surface-100, #eee);
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  white-space: nowrap;
  pointer-events: none;
  z-index: 10;
}

.no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
}
</style>
