<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  type ChartData,
  type ChartOptions,
} from 'chart.js'
import type { DebateTrendPoint } from '@/types/debate'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler)

interface Props {
  points: DebateTrendPoint[]
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  height: 200,
})

function directionColor(dir: string): string {
  if (dir === 'bullish') return '#22c55e'
  if (dir === 'bearish') return '#ef4444'
  return '#eab308'
}

const chartData = computed<ChartData<'line'>>(() => {
  const labels = props.points.map((p) =>
    new Date(p.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  )
  const data = props.points.map((p) => p.confidence * 100)
  const colors = props.points.map((p) => directionColor(p.direction))

  return {
    labels,
    datasets: [
      {
        data,
        borderColor: colors,
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        pointBackgroundColor: colors,
        pointBorderColor: colors,
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.3,
        fill: true,
        segment: {
          borderColor: (ctx) => {
            const idx = ctx.p1DataIndex
            return colors[idx] ?? '#3b82f6'
          },
        },
      },
    ],
  }
})

const chartOptions = computed<ChartOptions<'line'>>(() => ({
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    y: {
      min: 0,
      max: 100,
      ticks: {
        callback: (val) => `${val}%`,
        color: '#888',
        font: { size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.06)' },
    },
    x: {
      ticks: {
        color: '#888',
        font: { size: 10 },
        maxRotation: 45,
      },
      grid: { display: false },
    },
  },
  plugins: {
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const pt = props.points[ctx.dataIndex]
          const dir = pt.direction.charAt(0).toUpperCase() + pt.direction.slice(1)
          const fallback = pt.is_fallback ? ' (fallback)' : ''
          return `${dir}: ${(ctx.parsed.y ?? 0).toFixed(0)}%${fallback}`
        },
      },
    },
    legend: { display: false },
  },
}))
</script>

<template>
  <div class="trend-chart" :style="{ height: `${height}px` }">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<style scoped>
.trend-chart {
  width: 100%;
}
</style>
