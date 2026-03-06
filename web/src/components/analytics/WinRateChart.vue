<script setup lang="ts">
import { computed } from 'vue'
import type { WinRateResult } from '@/types'

interface Props {
  data: WinRateResult[]
}

const props = defineProps<Props>()

const chartWidth = 400
const chartHeight = 200
const padding = { top: 20, right: 20, bottom: 50, left: 20 }
const barGap = 30

const bars = computed(() => {
  if (props.data.length === 0) return []
  const areaWidth = chartWidth - padding.left - padding.right
  const areaHeight = chartHeight - padding.top - padding.bottom
  const barWidth = Math.min(80, (areaWidth - barGap * (props.data.length - 1)) / props.data.length)
  const totalBarsWidth = barWidth * props.data.length + barGap * (props.data.length - 1)
  const startX = padding.left + (areaWidth - totalBarsWidth) / 2

  return props.data.map((d, i) => {
    const x = startX + i * (barWidth + barGap)
    const height = d.win_rate * areaHeight
    const y = padding.top + areaHeight - height
    return {
      x,
      y,
      width: barWidth,
      height: Math.max(height, 2),
      color: directionColor(d.direction),
      label: d.direction,
      rate: `${(d.win_rate * 100).toFixed(1)}%`,
      detail: `${d.winners}/${d.total_contracts}`,
      labelX: x + barWidth / 2,
    }
  })
})

function directionColor(dir: string): string {
  if (dir === 'bullish') return 'var(--accent-green)'
  if (dir === 'bearish') return 'var(--accent-red)'
  return 'var(--accent-yellow)'
}
</script>

<template>
  <div class="chart-panel" data-testid="analytics-win-rate">
    <h3>Win Rate by Direction</h3>
    <div v-if="data.length === 0" class="panel-empty">No outcome data yet</div>
    <svg
      v-else
      :viewBox="`0 0 ${chartWidth} ${chartHeight}`"
      class="chart-svg"
      preserveAspectRatio="xMidYMid meet"
    >
      <rect
        v-for="bar in bars"
        :key="bar.label"
        :x="bar.x"
        :y="bar.y"
        :width="bar.width"
        :height="bar.height"
        :fill="bar.color"
        rx="3"
      />
      <text
        v-for="bar in bars"
        :key="'rate-' + bar.label"
        :x="bar.labelX"
        :y="bar.y - 6"
        text-anchor="middle"
        class="bar-label"
      >{{ bar.rate }}</text>
      <text
        v-for="bar in bars"
        :key="'name-' + bar.label"
        :x="bar.labelX"
        :y="chartHeight - padding.bottom + 18"
        text-anchor="middle"
        class="bar-axis-label"
      >{{ bar.label }}</text>
      <text
        v-for="bar in bars"
        :key="'detail-' + bar.label"
        :x="bar.labelX"
        :y="chartHeight - padding.bottom + 34"
        text-anchor="middle"
        class="bar-detail"
      >{{ bar.detail }}</text>
    </svg>
  </div>
</template>

<style scoped>
.chart-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.chart-panel h3 {
  font-size: 0.95rem;
  margin: 0 0 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.chart-svg {
  width: 100%;
  height: auto;
}

.bar-label {
  fill: var(--p-surface-100, #eee);
  font-size: 13px;
  font-family: var(--font-mono);
  font-weight: 600;
}

.bar-axis-label {
  fill: var(--p-surface-300, #aaa);
  font-size: 12px;
  text-transform: capitalize;
}

.bar-detail {
  fill: var(--p-surface-500, #666);
  font-size: 11px;
  font-family: var(--font-mono);
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
