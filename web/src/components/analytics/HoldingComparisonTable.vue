<script setup lang="ts">
import { computed } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import type { HoldingPeriodComparison } from '@/types'

interface Props {
  data: HoldingPeriodComparison[]
}

const props = defineProps<Props>()

const keyedData = computed(() =>
  props.data.map(d => ({ ...d, _rowKey: `${d.holding_days}-${d.direction}` })),
)

const bestSharpeIdx = computed(() => {
  if (props.data.length === 0) return -1
  return props.data.reduce(
    (best, row, i) => (row.sharpe_like > props.data[best].sharpe_like ? i : best),
    0,
  )
})

function rowClass(data: HoldingPeriodComparison & { _rowKey?: string }): string | undefined {
  const idx = keyedData.value.findIndex(d => d._rowKey === data._rowKey)
  return idx === bestSharpeIdx.value ? 'best-row' : undefined
}

function formatReturnPct(val: number): string {
  const prefix = val >= 0 ? '+' : ''
  return `${prefix}${val.toFixed(1)}%`
}

function directionSeverity(dir: string): 'success' | 'danger' | 'warn' {
  if (dir === 'bullish') return 'success'
  if (dir === 'bearish') return 'danger'
  return 'warn'
}
</script>

<template>
  <div class="table-panel" data-testid="holding-comparison-table">
    <h3>Holding Period Comparison</h3>
    <div v-if="data.length === 0" class="panel-empty">No holding period comparison data available</div>
    <DataTable
      v-else
      :value="keyedData"
      dataKey="_rowKey"
      :rows="20"
      :rowClass="rowClass"
      class="comparison-table"
    >
      <Column field="holding_days" header="Days" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono">{{ row.holding_days }}d</span>
        </template>
      </Column>
      <Column field="direction" header="Direction" :sortable="true">
        <template #body="{ data: row }">
          <Tag :value="row.direction" :severity="directionSeverity(row.direction)" />
        </template>
      </Column>
      <Column field="avg_return" header="Avg Return" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono" :class="row.avg_return >= 0 ? 'val-green' : 'val-red'">
            {{ formatReturnPct(row.avg_return) }}
          </span>
        </template>
      </Column>
      <Column field="median_return" header="Median" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono" :class="row.median_return >= 0 ? 'val-green' : 'val-red'">
            {{ formatReturnPct(row.median_return) }}
          </span>
        </template>
      </Column>
      <Column field="win_rate" header="Win Rate" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono">{{ (row.win_rate * 100).toFixed(1) }}%</span>
        </template>
      </Column>
      <Column field="sharpe_like" header="Sharpe" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono" :class="row.sharpe_like >= 0 ? 'val-green' : 'val-red'">
            {{ row.sharpe_like.toFixed(2) }}
          </span>
        </template>
      </Column>
      <Column field="max_loss" header="Max Loss" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono val-red">{{ formatReturnPct(row.max_loss) }}</span>
        </template>
      </Column>
      <Column field="count" header="Samples" :sortable="true" />
    </DataTable>
  </div>
</template>

<style scoped>
.table-panel {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.table-panel h3 {
  font-size: 0.95rem;
  margin: 0 0 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.comparison-table {
  font-size: 0.85rem;
}

.comparison-table :deep(.best-row) {
  background: rgba(34, 197, 94, 0.08) !important;
}

.mono {
  font-family: var(--font-mono);
}

.val-green {
  color: var(--accent-green);
}

.val-red {
  color: var(--accent-red);
}

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
