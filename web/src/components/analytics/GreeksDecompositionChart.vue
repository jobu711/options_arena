<script setup lang="ts">
import { computed } from 'vue'
import Chart from 'primevue/chart'
import type { GreeksDecompositionResult } from '@/types'

interface Props {
  data: GreeksDecompositionResult[]
}

const props = defineProps<Props>()

const chartData = computed(() => {
  if (props.data.length === 0) return null
  return {
    labels: props.data.map(d => d.group_key),
    datasets: [
      {
        label: 'Delta P&L',
        data: props.data.map(d => d.delta_pnl),
        backgroundColor: 'rgba(59, 130, 246, 0.7)',
        borderRadius: 4,
      },
      {
        label: 'Residual P&L',
        data: props.data.map(d => d.residual_pnl),
        backgroundColor: 'rgba(168, 85, 247, 0.7)',
        borderRadius: 4,
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
        font: { size: 11 },
      },
    },
    tooltip: {
      callbacks: {
        afterLabel: (ctx: { dataIndex: number }) => {
          const item = props.data[ctx.dataIndex]
          return `Total P&L: ${item.total_pnl >= 0 ? '+' : ''}${item.total_pnl.toFixed(1)}% | n=${item.count}`
        },
      },
    },
  },
  scales: {
    x: {
      stacked: true,
      ticks: {
        color: '#aaa',
        font: { size: 11 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: {
      stacked: true,
      ticks: {
        color: '#888',
        callback: (val: number) => `${val >= 0 ? '+' : ''}${val}%`,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
  },
}))
</script>

<template>
  <div class="chart-panel" data-testid="greeks-decomposition-chart">
    <h3>Greeks P&L Decomposition</h3>
    <div v-if="!chartData" class="panel-empty">No Greeks decomposition data available</div>
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
  height: 300px;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
