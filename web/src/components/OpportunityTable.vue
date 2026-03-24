<script setup lang="ts">
import { ref, computed } from 'vue'
import DataTable, { type DataTableRowClickEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import DirectionBadge from '@/components/DirectionBadge.vue'
import PipelineStatus from '@/components/PipelineStatus.vue'
import DeskCard from '@/components/DeskCard.vue'
import type { PipelineTicker } from '@/types/recommendation'

interface Props {
  tickers: PipelineTicker[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  selectTicker: [ticker: string]
  analyzeTicker: [ticker: string]
  selectionChange: [tickers: string[]]
}>()

const selectedRows = ref<PipelineTicker[]>([])

const tickerCount = computed(() => props.tickers.length)

function onRowClick(event: DataTableRowClickEvent): void {
  const row = event.data as PipelineTicker
  emit('selectTicker', row.ticker)
}

function onSelectionUpdate(rows: PipelineTicker[]): void {
  selectedRows.value = rows
  emit('selectionChange', rows.map((r) => r.ticker))
}

function onAnalyze(ticker: string): void {
  emit('analyzeTicker', ticker)
}

function rowClass(data: PipelineTicker): string {
  const isSelected = selectedRows.value.some((r) => r.ticker === data.ticker)
  return isSelected ? 'row--selected' : ''
}

function formatConfidence(confidence: number | null): string {
  if (confidence === null) return '--'
  return (confidence * 100).toFixed(0) + '%'
}
</script>

<template>
  <DeskCard title="OPPORTUNITY PIPELINE" :full-width="true">
    <template #status>
      <span class="ticker-count" data-testid="ticker-count">{{ tickerCount }} tickers</span>
    </template>

    <div v-if="tickers.length === 0" class="empty-state" data-testid="empty-state">
      <i class="pi pi-inbox empty-state__icon" />
      <p class="empty-state__text">No tickers in pipeline</p>
      <p class="empty-state__hint">Run a scan to populate the opportunity pipeline.</p>
    </div>

    <DataTable
      v-else
      :value="tickers"
      :selection="selectedRows"
      @update:selection="onSelectionUpdate"
      sortMode="single"
      sortField="composite_score"
      :sortOrder="-1"
      :scrollable="true"
      scrollHeight="flex"
      :virtualScrollerOptions="tickers.length > 1000 ? { itemSize: 44 } : undefined"
      dataKey="ticker"
      :rowClass="rowClass"
      @row-click="onRowClick"
      class="opportunity-table"
      data-testid="opportunity-table"
    >
      <Column selectionMode="multiple" :style="{ width: '3rem' }" />

      <Column field="ticker" header="Ticker" :sortable="true" :style="{ width: '100px' }">
        <template #body="{ data }">
          <span class="ticker-cell mono" data-testid="ticker-cell">{{ (data as PipelineTicker).ticker }}</span>
        </template>
      </Column>

      <Column field="composite_score" header="Score" :sortable="true" :style="{ width: '80px' }">
        <template #body="{ data }">
          <span class="mono">{{ (data as PipelineTicker).composite_score.toFixed(1) }}</span>
        </template>
      </Column>

      <Column field="direction" header="Direction" :sortable="true" :style="{ width: '110px' }">
        <template #body="{ data }">
          <DirectionBadge :direction="(data as PipelineTicker).direction" />
        </template>
      </Column>

      <Column field="direction_confidence" header="Confidence" :sortable="true" :style="{ width: '100px' }">
        <template #body="{ data }">
          <span class="mono">{{ formatConfidence((data as PipelineTicker).direction_confidence) }}</span>
        </template>
      </Column>

      <Column field="sector" header="Sector" :sortable="true" :style="{ width: '160px' }">
        <template #body="{ data }">
          <span>{{ (data as PipelineTicker).sector ?? '--' }}</span>
        </template>
      </Column>

      <Column field="stage" header="Stage" :sortable="true" :style="{ width: '120px' }">
        <template #body="{ data }">
          <PipelineStatus :stage="(data as PipelineTicker).stage" />
        </template>
      </Column>

      <Column header="Action" :style="{ width: '110px' }">
        <template #body="{ data }">
          <Button
            v-if="(data as PipelineTicker).stage === 'scored'"
            label="Analyze"
            icon="pi pi-play"
            severity="info"
            size="small"
            text
            @click.stop="onAnalyze((data as PipelineTicker).ticker)"
            data-testid="analyze-btn"
          />
          <Button
            v-else-if="(data as PipelineTicker).stage === 'ready'"
            label="View"
            icon="pi pi-eye"
            severity="success"
            size="small"
            text
            @click.stop="onAnalyze((data as PipelineTicker).ticker)"
            data-testid="view-btn"
          />
          <i
            v-else-if="(data as PipelineTicker).stage === 'analyzing'"
            class="pi pi-spinner spin-icon"
            data-testid="analyzing-spinner"
          />
          <Button
            v-else
            label="--"
            size="small"
            text
            disabled
          />
        </template>
      </Column>
    </DataTable>
  </DeskCard>
</template>

<style scoped>
.ticker-count {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
}

.mono {
  font-family: var(--font-mono);
}

.ticker-cell {
  font-weight: 700;
  letter-spacing: 0.04em;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  gap: 0.5rem;
}

.empty-state__icon {
  font-size: 2.5rem;
  color: var(--p-surface-500, #666);
}

.empty-state__text {
  font-size: 1rem;
  font-weight: 600;
  color: var(--p-surface-300, #aaa);
  margin: 0;
}

.empty-state__hint {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
  margin: 0;
}

.spin-icon {
  animation: spin 1s linear infinite;
  font-size: 1rem;
  color: var(--p-surface-400, #888);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

:deep(.row--selected) {
  background: var(--p-surface-700) !important;
}

.opportunity-table {
  font-size: 0.875rem;
}
</style>
