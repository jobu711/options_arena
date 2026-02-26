<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DataTable, { type DataTableSortEvent, type DataTablePageEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import DirectionBadge from '@/components/DirectionBadge.vue'
import TickerDrawer from '@/components/TickerDrawer.vue'
import { useScanStore } from '@/stores/scan'
import type { TickerScore } from '@/types'

const route = useRoute()
const router = useRouter()
const scanStore = useScanStore()

const scanId = Number(route.params.id)

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

// Batch selection (wired in #127)
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
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Scan #{{ scanId }} Results</h1>
      <span class="total-count mono" v-if="scanStore.totalScores > 0">
        {{ scanStore.totalScores }} tickers
      </span>
    </div>

    <!-- Filters -->
    <div class="filters">
      <InputText
        v-model="search"
        placeholder="Search ticker..."
        size="small"
        class="search-input"
      />
      <Select
        v-model="direction"
        :options="directionOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="Direction"
        size="small"
        @change="onDirectionChange()"
      />
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
    >
      <Column selectionMode="multiple" :style="{ width: '3rem' }" />
      <Column field="ticker" header="Ticker" :sortable="true" :style="{ width: '100px' }">
        <template #body="{ data }">
          <span class="ticker-cell mono">{{ data.ticker }}</span>
        </template>
      </Column>
      <Column field="composite_score" header="Score" :sortable="true" :style="{ width: '80px' }">
        <template #body="{ data }">
          <span class="mono">{{ data.composite_score.toFixed(1) }}</span>
        </template>
      </Column>
      <Column field="direction" header="Direction" :sortable="true" :style="{ width: '110px' }">
        <template #body="{ data }">
          <DirectionBadge :direction="data.direction" />
        </template>
      </Column>
      <template #empty>
        <div class="empty-msg">No results found matching your filters.</div>
      </template>
    </DataTable>

    <!-- Ticker Drawer -->
    <TickerDrawer
      v-model:visible="drawerVisible"
      :score="selectedScore"
      :scan-id="scanId"
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
}

.search-input {
  min-width: 200px;
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
