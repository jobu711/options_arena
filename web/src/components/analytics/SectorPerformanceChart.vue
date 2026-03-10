<script setup lang="ts">
import { computed } from 'vue'
import Chart from 'primevue/chart'
import type { SectorPerformanceResult } from '@/types'

interface Props {
  data: SectorPerformanceResult[]
}

const props = defineProps<Props>()

const sortedData = computed(() =>
  [...props.data].sort((a, b) => b.win_rate_pct - a.win_rate_pct),
)

const chartData = computed(() => {
  if (sortedData.value.length === 0) return null
  return {
    labels: sortedData.value.map(d => d.sector),
    datasets: [
      {
        label: 'Win Rate %',
        data: sortedData.value.map(d => d.win_rate_pct),
        backgroundColor: sortedData.value.map(d =>
          d.win_rate_pct >= 50 ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)',
        ),
        borderRadius: 4,
        barThickness: 20,
      },
    ],
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  indexAxis: 'y' as const,
  plugins: {
    legend: {
      display: false,
    },
    tooltip: {
      callbacks: {
        afterLabel: (ctx: { dataIndex: number }) => {
          const item = sortedData.value[ctx.dataIndex]
          return `Avg Return: ${item.avg_return_pct >= 0 ? '+' : ''}${item.avg_return_pct.toFixed(1)}% | n=${item.total}`
        },
      },
    },
  },
  scales: {
    x: {
      ticks: {
        color: '#888',
        callback: (val: number) => `${val}%`,
        font: { family: "'JetBrains Mono', monospace", size: 10 },
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
      min: 0,
      max: 100,
    },
    y: {
      ticks: {
        color: '#aaa',
        font: { size: 11 },
      },
      grid: { display: false },
    },
  },
}))
</script>

<template>
  <div class="chart-panel" data-testid="sector-performance-chart">
    <h3>Win Rate by Sector</h3>
    <div v-if="!chartData" class="panel-empty">No sector performance data available</div>
    <div v-else class="chart-container" :style="{ height: Math.max(200, sortedData.length * 32) + 'px' }">
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
  min-height: 200px;
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
