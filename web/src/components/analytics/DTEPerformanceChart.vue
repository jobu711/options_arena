<script setup lang="ts">
import { computed } from 'vue'
import Chart from 'primevue/chart'
import type { DTEBucketResult } from '@/types'

interface Props {
  data: DTEBucketResult[]
}

const props = defineProps<Props>()

const chartData = computed(() => {
  if (props.data.length === 0) return null
  return {
    labels: props.data.map(d => `${d.dte_min}-${d.dte_max}d`),
    datasets: [
      {
        label: 'Win Rate %',
        data: props.data.map(d => d.win_rate_pct),
        backgroundColor: props.data.map(d =>
          d.win_rate_pct >= 50 ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)',
        ),
        borderRadius: 4,
        yAxisID: 'y',
      },
      {
        label: 'Avg Return %',
        data: props.data.map(d => d.avg_return_pct),
        type: 'line' as const,
        borderColor: '#3b82f6',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: '#3b82f6',
        yAxisID: 'y1',
      },
    ],
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      labels: {
        color: '#aaa',
        font: { size: 10 },
      },
    },
    tooltip: {
      callbacks: {
        afterLabel: (ctx: { dataIndex: number }) => {
          const item = props.data[ctx.dataIndex]
          return `n=${item.total}`
        },
      },
    },
  },
  scales: {
    x: {
      ticks: {
        color: '#888',
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: {
      position: 'left' as const,
      ticks: {
        color: '#888',
        callback: (val: number) => `${val}%`,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
      min: 0,
      max: 100,
    },
    y1: {
      position: 'right' as const,
      ticks: {
        color: '#3b82f6',
        callback: (val: number) => `${val >= 0 ? '+' : ''}${val}%`,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { display: false },
    },
  },
}))
</script>

<template>
  <div class="chart-panel" data-testid="dte-performance-chart">
    <h3>DTE Bucket Performance</h3>
    <div v-if="!chartData" class="panel-empty">No DTE performance data available</div>
    <div v-else class="chart-container">
      <Chart type="bar" :data="chartData" :options="chartOptions" />
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

.chart-panel h3 {
  font-size: 0.95rem;
  margin: 0 0 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.chart-container {
  height: 280px;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
