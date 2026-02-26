<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DataTable, { type DataTableSortEvent, type DataTablePageEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Button from 'primevue/button'
import DirectionBadge from '@/components/DirectionBadge.vue'
import TickerDrawer from '@/components/TickerDrawer.vue'
import DebateProgressModal from '@/components/DebateProgressModal.vue'
import { useScanStore } from '@/stores/scan'
import { useDebateStore } from '@/stores/debate'
import { useOperationStore } from '@/stores/operation'
import { useWebSocket } from '@/composables/useWebSocket'
import { ApiError } from '@/composables/useApi'
import type { TickerScore } from '@/types'
import type { DebateEvent, BatchEvent } from '@/types/ws'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const scanStore = useScanStore()
const debateStore = useDebateStore()
const operationStore = useOperationStore()

const scanId = Number(route.params.id)

// Modal state
const debateModalVisible = ref(false)
const debatingTicker = ref('')
const batchModalVisible = ref(false)

// WebSocket close handles for cleanup
let debateWsClose: (() => void) | null = null
let batchWsClose: (() => void) | null = null

// Single debate
async function startDebate(ticker: string): Promise<void> {
  try {
    debatingTicker.value = ticker
    debateModalVisible.value = true
    const debateId = await debateStore.startDebate(ticker, scanId)

    const { close } = useWebSocket<DebateEvent>({
      url: `/ws/debate/${debateId}`,
      onMessage(event) {
        switch (event.type) {
          case 'agent':
            debateStore.updateAgentProgress(event)
            break
          case 'error':
            debateStore.setDebateError(event.message)
            break
          case 'complete':
            debateStore.setDebateComplete(event.debate_id)
            close()  // Stop reconnection — terminal event
            debateModalVisible.value = false
            router.push(`/debate/${event.debate_id}`)
            break
        }
      },
    })
    debateWsClose = close
  } catch (e) {
    debateModalVisible.value = false
    debateStore.reset()
    const msg = e instanceof ApiError ? e.message : 'Failed to start debate'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

// Batch debate
async function startBatchDebate(tickers: string[] | null, limit: number): Promise<void> {
  try {
    batchModalVisible.value = true
    operationStore.start('batch_debate')
    const batchId = await debateStore.startBatchDebate(scanId, tickers, limit)

    const { close } = useWebSocket<BatchEvent>({
      url: `/ws/batch/${batchId}`,
      onMessage(event) {
        switch (event.type) {
          case 'batch_progress':
            debateStore.updateBatchProgress(event)
            break
          case 'agent':
            debateStore.updateBatchAgentProgress(event)
            break
          case 'error':
            debateStore.setBatchError(event.message)
            break
          case 'batch_complete':
            debateStore.setBatchComplete(event.results)
            operationStore.finish()
            close()  // Stop reconnection — terminal event
            break
        }
      },
    })
    batchWsClose = close
  } catch (e) {
    batchModalVisible.value = false
    debateStore.resetBatch()
    operationStore.finish()
    const msg = e instanceof ApiError ? e.message : 'Failed to start batch debate'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

function onDebateSelected(): void {
  const tickers = selectedTickers.value.map((s) => s.ticker)
  void startBatchDebate(tickers, tickers.length)
}

function onDebateTop5(): void {
  void startBatchDebate(null, 5)
}

function onBatchModalClose(): void {
  batchModalVisible.value = false
  debateStore.resetBatch()
}

const anyBusy = computed(
  () => debateStore.isDebating || debateStore.isBatching || operationStore.inProgress,
)

// URL-synced filter state
const search = ref((route.query.search as string) ?? '')
const direction = ref<string | undefined>((route.query.direction as string) ?? undefined)
const sortField = ref((route.query.sort as string) ?? 'composite_score')
const sortOrder = ref(route.query.order === 'asc' ? 1 : -1)
const page = ref(Number(route.query.page) || 1)

const directionOptions = [
  { label: 'All', value: undefined },
  { label: 'Bullish', value: 'bullish' },
  { label: 'Bearish', value: 'bearish' },
  { label: 'Neutral', value: 'neutral' },
]

// Drawer state
const drawerVisible = ref(false)
const selectedScore = ref<TickerScore | null>(null)

// Batch selection
const selectedTickers = ref<TickerScore[]>([])

function buildParams(): Record<string, string | number | undefined> {
  return {
    page: page.value,
    page_size: 50,
    sort: sortField.value,
    order: sortOrder.value === 1 ? 'asc' : 'desc',
    direction: direction.value,
    search: search.value || undefined,
  }
}

function syncUrl(): void {
  const query: Record<string, string> = {}
  if (search.value) query.search = search.value
  if (direction.value) query.direction = direction.value
  if (sortField.value !== 'composite_score') query.sort = sortField.value
  if (sortOrder.value === 1) query.order = 'asc'
  if (page.value > 1) query.page = String(page.value)
  router.replace({ query })
}

async function loadScores(): Promise<void> {
  await scanStore.fetchScores(scanId, buildParams())
}

function onSort(event: DataTableSortEvent): void {
  if (typeof event.sortField === 'string') {
    sortField.value = event.sortField
  }
  sortOrder.value = event.sortOrder === 1 ? 1 : -1
  page.value = 1
  syncUrl()
  void loadScores()
}

function onPage(event: DataTablePageEvent): void {
  page.value = event.page + 1 // PrimeVue pages are 0-indexed
  syncUrl()
  void loadScores()
}

function onSearch(): void {
  page.value = 1
  syncUrl()
  void loadScores()
}

function onDirectionChange(): void {
  page.value = 1
  syncUrl()
  void loadScores()
}

function onRowClick(event: { data: TickerScore }): void {
  selectedScore.value = event.data
  drawerVisible.value = true
}

// Debounce search input
let searchTimeout: ReturnType<typeof setTimeout> | null = null
watch(search, () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(onSearch, 300)
})

onMounted(() => void loadScores())
onUnmounted(() => {
  debateWsClose?.()
  batchWsClose?.()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Scan #{{ scanId }} Results</h1>
      <span class="total-count mono" v-if="scanStore.totalScores > 0">
        {{ scanStore.totalScores }} tickers
      </span>
    </div>

    <!-- Filters + Batch Actions -->
    <div class="filters">
      <InputText
        v-model="search"
        placeholder="Search ticker..."
        size="small"
        class="search-input"
        data-testid="ticker-search"
      />
      <Select
        v-model="direction"
        :options="directionOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="Direction"
        size="small"
        data-testid="direction-filter"
        @change="onDirectionChange()"
      />
      <div class="batch-actions">
        <Button
          v-if="selectedTickers.length > 0"
          :label="`Debate Selected (${selectedTickers.length})`"
          icon="pi pi-comments"
          severity="info"
          size="small"
          :disabled="anyBusy"
          data-testid="batch-debate-btn"
          @click="onDebateSelected()"
        />
        <Button
          label="Debate Top 5"
          icon="pi pi-bolt"
          severity="secondary"
          size="small"
          :disabled="anyBusy"
          data-testid="batch-debate-top5-btn"
          @click="onDebateTop5()"
        />
      </div>
    </div>

    <!-- Data Table -->
    <DataTable
      :value="scanStore.scores"
      :loading="scanStore.loading"
      dataKey="ticker"
      :paginator="true"
      :rows="50"
      :rowsPerPageOptions="[25, 50, 100]"
      :totalRecords="scanStore.totalScores"
      :lazy="true"
      sortMode="single"
      :sortField="sortField"
      :sortOrder="sortOrder"
      selectionMode="multiple"
      v-model:selection="selectedTickers"
      :virtualScrollerOptions="scanStore.totalScores > 1000 ? { itemSize: 40 } : undefined"
      @sort="onSort"
      @page="onPage"
      @row-click="onRowClick"
      class="results-table"
      data-testid="scan-results-table"
    >
      <Column selectionMode="multiple" :style="{ width: '3rem' }" />
      <Column field="ticker" header="Ticker" :sortable="true" :style="{ width: '100px' }">
        <template #body="{ data }">
          <span class="ticker-cell mono" data-testid="ticker-cell">{{ data.ticker }}</span>
        </template>
      </Column>
      <Column field="composite_score" header="Score" :sortable="true" :style="{ width: '80px' }">
        <template #body="{ data }">
          <span class="mono" data-testid="composite-score">{{ data.composite_score.toFixed(1) }}</span>
        </template>
      </Column>
      <Column field="direction" header="Direction" :sortable="true" :style="{ width: '110px' }">
        <template #body="{ data }">
          <DirectionBadge :direction="data.direction" />
        </template>
      </Column>
      <Column header="" :style="{ width: '100px' }">
        <template #body="{ data }">
          <Button
            label="Debate"
            icon="pi pi-comments"
            severity="info"
            size="small"
            text
            :disabled="anyBusy"
            :data-testid="`debate-btn-${data.ticker}`"
            @click.stop="startDebate(data.ticker)"
          />
        </template>
      </Column>
      <template #empty>
        <div class="empty-msg" data-testid="empty-state">No results found matching your filters.</div>
      </template>
    </DataTable>

    <!-- Ticker Drawer -->
    <TickerDrawer
      v-model:visible="drawerVisible"
      :score="selectedScore"
      :scan-id="scanId"
    />

    <!-- Single Debate Progress Modal -->
    <DebateProgressModal
      v-model:visible="debateModalVisible"
      :ticker="debatingTicker"
      :agents="debateStore.agentProgress"
      :error="debateStore.error"
    />

    <!-- Batch Debate Progress Modal -->
    <DebateProgressModal
      :visible="batchModalVisible"
      :batch-mode="true"
      :batch-tickers="debateStore.batchTickers"
      :batch-results="debateStore.batchResults"
      :batch-complete="debateStore.batchComplete"
      :error="debateStore.error"
      @update:visible="onBatchModalClose()"
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}

.page-header h1 {
  margin: 0;
}

.total-count {
  font-size: 0.9rem;
  color: var(--p-surface-400, #888);
}

.filters {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  align-items: center;
}

.search-input {
  min-width: 200px;
}

.batch-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.results-table :deep(tr) {
  cursor: pointer;
}

.results-table :deep(tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.ticker-cell {
  font-weight: 600;
}

.mono {
  font-family: var(--font-mono);
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}
</style>
