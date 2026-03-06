<script setup lang="ts">
import { computed } from 'vue'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import type { HoldingPeriodResult } from '@/types'

interface Props {
  data: HoldingPeriodResult[]
  direction: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:direction': [direction: string] }>()

const directionOptions = [
  { label: 'All', value: 'all' },
  { label: 'Bullish', value: 'bullish' },
  { label: 'Bearish', value: 'bearish' },
]

const keyedData = computed(() =>
  props.data.map(d => ({ ...d, _rowKey: `${d.holding_days}-${d.direction}` }))
)

const bestWinRateIdx = computed(() => {
  if (props.data.length === 0) return -1
  return props.data.reduce((best, row, i) =>
    row.win_rate > props.data[best].win_rate ? i : best, 0)
})

function rowClass(data: HoldingPeriodResult & { _rowKey?: string }): string | undefined {
  const idx = keyedData.value.findIndex(d => d._rowKey === data._rowKey)
  return idx === bestWinRateIdx.value ? 'best-row' : undefined
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
  <div class="table-panel" data-testid="analytics-holding">
    <div class="panel-header">
      <h3>Holding Period Analysis</h3>
      <Select
        :modelValue="direction"
        :options="directionOptions"
        optionLabel="label"
        optionValue="value"
        class="dir-select"
        data-testid="direction-select"
        @update:modelValue="emit('update:direction', $event)"
      />
    </div>
    <div v-if="data.length === 0" class="panel-empty">No holding period data available</div>
    <DataTable
      v-else
      :value="keyedData"
      dataKey="_rowKey"
      :rows="20"
      :rowClass="rowClass"
      class="holding-table"
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
      <Column field="avg_return_pct" header="Avg Return" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono" :class="row.avg_return_pct >= 0 ? 'val-green' : 'val-red'">
            {{ formatReturnPct(row.avg_return_pct) }}
          </span>
        </template>
      </Column>
      <Column field="median_return_pct" header="Median" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono" :class="row.median_return_pct >= 0 ? 'val-green' : 'val-red'">
            {{ formatReturnPct(row.median_return_pct) }}
          </span>
        </template>
      </Column>
      <Column field="win_rate" header="Win Rate" :sortable="true">
        <template #body="{ data: row }">
          <span class="mono">{{ (row.win_rate * 100).toFixed(1) }}%</span>
        </template>
      </Column>
      <Column field="sample_size" header="Samples" :sortable="true" />
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

.dir-select {
  width: 110px;
}

.holding-table {
  font-size: 0.85rem;
}

.holding-table :deep(.best-row) {
  background: rgba(34, 197, 94, 0.08) !important;
}

.mono { font-family: var(--font-mono); }
.val-green { color: var(--accent-green); }
.val-red { color: var(--accent-red); }

.panel-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
  padding: 2rem 0;
  text-align: center;
}
</style>
