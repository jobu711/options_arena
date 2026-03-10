<script setup lang="ts">
import { computed } from 'vue'
import Chart from 'primevue/chart'
import type { DrawdownPoint } from '@/types'

interface Props {
  data: DrawdownPoint[]
}

const props = defineProps<Props>()

const chartData = computed(() => {
  if (props.data.length === 0) return null
  return {
    labels: props.data.map(p => p.date),
    datasets: [
      {
        label: 'Drawdown %',
        data: props.data.map(p => p.drawdown_pct),
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.15)',
        fill: true,
        tension: 0.3,
        pointRadius: props.data.length > 50 ? 0 : 3,
        pointHoverRadius: 5,
        borderWidth: 2,
      },
    ],
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      display: false,
    },
    tooltip: {
      callbacks: {
        label: (ctx: { parsed: { y: number }; dataIndex: number }) => {
          const point = props.data[ctx.dataIndex]
          return `Drawdown: ${ctx.parsed.y.toFixed(1)}% (peak: ${point.peak_value.toFixed(1)}%)`
        },
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
        callback: (val: number) => `${val}%`,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
      max: 0,
    },
  },
}))
</script>

<template>
  <div class="chart-panel" data-testid="drawdown-chart">
    <h3>Drawdown</h3>
    <div v-if="!chartData" class="panel-empty">No drawdown data available</div>
    <div v-else class="chart-container">
      <Chart type="line" :data="chartData" :options="chartOptions" />
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
  height: 200px;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
