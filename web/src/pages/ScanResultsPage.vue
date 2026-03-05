<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DataTable, { type DataTableSortEvent, type DataTablePageEvent } from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Panel from 'primevue/panel'
import ThemeChips from '@/components/scan/ThemeChips.vue'
import SectorTree from '@/components/SectorTree.vue'
import DirectionBadge from '@/components/DirectionBadge.vue'
import SparklineChart from '@/components/SparklineChart.vue'
import RegimeBanner from '@/components/RegimeBanner.vue'
import DimensionalScoreBars from '@/components/DimensionalScoreBars.vue'
import ScanFilterPanel from '@/components/ScanFilterPanel.vue'
import FilterPresets from '@/components/FilterPresets.vue'
import TickerDrawer from '@/components/TickerDrawer.vue'
import DebateProgressModal from '@/components/DebateProgressModal.vue'
import { useScanStore } from '@/stores/scan'
import { useDebateStore } from '@/stores/debate'
import { useOperationStore } from '@/stores/operation'
import { useWatchlistStore } from '@/stores/watchlist'
import { useWebSocket } from '@/composables/useWebSocket'
import { api, ApiError } from '@/composables/useApi'
import type { TickerScore, ScanRun, ScanDiff, TickerDelta, HistoryPoint, SectorHierarchy, ThemeInfo, FilterParams } from '@/types'
import type { DebateEvent, BatchEvent } from '@/types/ws'

/** Map GICS sector names to PrimeVue Tag severity values for color-coding. */
type TagSeverity = 'info' | 'success' | 'warn' | 'danger' | 'secondary' | 'contrast'

const SECTOR_COLORS: Record<string, TagSeverity | undefined> = {
  'Information Technology': 'info',
  'Health Care': 'success',
  'Financials': 'secondary',
  'Consumer Discretionary': 'warn',
  'Communication Services': 'contrast',
  'Industrials': undefined,
  'Consumer Staples': 'success',
  'Energy': 'danger',
  'Utilities': 'secondary',
  'Real Estate': 'warn',
  'Materials': 'contrast',
}

function sectorSeverity(sector: string | null): TagSeverity | undefined {
  if (!sector) return undefined
  return SECTOR_COLORS[sector] ?? 'info'
}

const route = useRoute()
const router = useRouter()
const toast = useToast()
const scanStore = useScanStore()
const debateStore = useDebateStore()
const operationStore = useOperationStore()
const watchlistStore = useWatchlistStore()

const scanId = Number(route.params.id)

// Modal state
const debateModalVisible = ref(false)
const debatingTicker = ref('')
const batchModalVisible = ref(false)

// WebSocket close handles for cleanup
let debateWsClose: (() => void) | null = null
let batchWsClose: (() => void) | null = null

// --- Scan comparison state ---
const compareScanId = ref<number | null>(
  route.query.compare ? Number(route.query.compare) : null,
)
const scanDiff = ref<ScanDiff | null>(null)
const diffLoading = ref(false)

// Build compare options from scan history (exclude current scan)
const compareOptions = computed(() => {
  const opts: Array<{ label: string; value: number | null }> = [
    { label: 'None', value: null },
  ]
  for (const scan of scanStore.scans) {
    if (scan.id !== scanId) {
      const dateStr = new Date(scan.started_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
      opts.push({ label: `Scan #${scan.id} (${dateStr})`, value: scan.id })
    }
  }
  return opts
})

// Lookup maps for fast access during rendering
const diffByTicker = computed<Map<string, TickerDelta>>(() => {
  const map = new Map<string, TickerDelta>()
  if (scanDiff.value) {
    for (const mover of scanDiff.value.movers) {
      map.set(mover.ticker, mover)
    }
  }
  return map
})

const addedTickers = computed<Set<string>>(() => {
  return new Set(scanDiff.value?.added ?? [])
})

const topMovers = computed<TickerDelta[]>(() => {
  if (!scanDiff.value) return []
  return scanDiff.value.movers.slice(0, 5)
})

async function fetchDiff(baseId: number): Promise<void> {
  diffLoading.value = true
  try {
    scanDiff.value = await api<ScanDiff>(`/api/scan/${scanId}/diff`, {
      params: { base_id: baseId },
    })
  } catch (e) {
    scanDiff.value = null
    const msg = e instanceof ApiError ? e.message : 'Failed to load comparison'
    toast.add({ severity: 'error', summary: 'Compare Error', detail: msg, life: 5000 })
  } finally {
    diffLoading.value = false
  }
}

function onCompareChange(): void {
  const query: Record<string, string> = { ...route.query as Record<string, string> }
  if (compareScanId.value !== null) {
    query.compare = String(compareScanId.value)
    void fetchDiff(compareScanId.value)
  } else {
    delete query.compare
    scanDiff.value = null
  }
  router.replace({ query })
}

/** Format a score change as a string: "+2.3" or "-1.5". */
function formatDelta(change: number): string {
  const sign = change >= 0 ? '+' : ''
  return `${sign}${change.toFixed(1)}`
}

/** CSS class for delta chip based on sign. */
function deltaClass(change: number): string {
  if (change > 0) return 'delta-positive'
  if (change < 0) return 'delta-negative'
  return 'delta-neutral'
}

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

// Sector + industry group filter state (hierarchical tree)
const sectorHierarchy = ref<SectorHierarchy[]>([])
const selectedSectorFilters = ref<string[]>([])
const selectedIndustryGroupFilters = ref<string[]>([])

async function fetchSectorOptions(): Promise<void> {
  try {
    sectorHierarchy.value = await api<SectorHierarchy[]>('/api/universe/sectors')
  } catch {
    sectorHierarchy.value = []
  }
}

function onSectorFilterChange(): void {
  page.value = 1
  syncUrl()
  void loadScores()
}

// Theme filter state
const availableThemes = ref<ThemeInfo[]>([])
const selectedThemeFilters = ref<string[]>([])

async function fetchThemeOptions(): Promise<void> {
  try {
    availableThemes.value = await api<ThemeInfo[]>('/api/universe/themes')
  } catch {
    availableThemes.value = []
  }
}

function onThemeFilterChange(themes: string[]): void {
  selectedThemeFilters.value = themes
  page.value = 1
  syncUrl()
  void loadScores()
}

// Dimensional filters state (ScanFilterPanel + FilterPresets)
const dimensionalFilters = ref<FilterParams>({})

function onDimensionalFilterChange(filters: FilterParams): void {
  dimensionalFilters.value = filters
  page.value = 1
  syncUrl()
  void loadScores()
}

function onPresetApplied(filters: FilterParams): void {
  dimensionalFilters.value = filters
  page.value = 1
  syncUrl()
  void loadScores()
}

function onClearAllFilters(): void {
  dimensionalFilters.value = {}
  page.value = 1
  syncUrl()
  void loadScores()
}

// Drawer state
const drawerVisible = ref(false)
const selectedScore = ref<TickerScore | null>(null)

// Batch selection
const selectedTickers = ref<TickerScore[]>([])

// Row expansion state
const expandedRows = ref<Record<string, boolean>>({})

// Sparkline history data (ticker -> last 10 scores)
const sparklineData = ref<Map<string, number[]>>(new Map())
const sparklineDirections = ref<Map<string, string>>(new Map())

/** Fetch score history for all tickers currently in the results table. */
async function fetchSparklineData(): Promise<void> {
  const tickers = scanStore.scores.map((s) => s.ticker)
  if (tickers.length === 0) return

  const results = await Promise.allSettled(
    tickers.map((ticker) =>
      api<HistoryPoint[]>(`/api/ticker/${ticker}/history`, { params: { limit: 10 } }),
    ),
  )

  const scores = new Map<string, number[]>()
  const directions = new Map<string, string>()
  for (let i = 0; i < tickers.length; i++) {
    const result = results[i]
    if (result.status === 'fulfilled' && result.value.length >= 2) {
      scores.set(tickers[i], result.value.map((p) => p.composite_score))
      const newest = result.value[0]
      directions.set(tickers[i], newest.direction)
    }
  }
  sparklineData.value = scores
  sparklineDirections.value = directions
}

function buildParams(): Record<string, string | number | undefined> {
  const params: Record<string, string | number | undefined> = {
    page: page.value,
    page_size: 50,
    sort: sortField.value,
    order: sortOrder.value === 1 ? 'asc' : 'desc',
    direction: direction.value,
    search: search.value || undefined,
  }
  if (selectedSectorFilters.value.length > 0) {
    params.sectors = selectedSectorFilters.value.join(',')
  }
  if (selectedIndustryGroupFilters.value.length > 0) {
    params.industry_groups = selectedIndustryGroupFilters.value.join(',')
  }
  if (selectedThemeFilters.value.length > 0) {
    params.themes = selectedThemeFilters.value.join(',')
  }
  // Dimensional filters (use > 0 to avoid falsy 0 suppression)
  const df = dimensionalFilters.value
  if (df.min_score != null && df.min_score > 0) params.min_score = df.min_score
  if (df.min_confidence != null && df.min_confidence > 0)
    params.min_confidence = df.min_confidence / 100 // slider is 0-100, API expects 0-1
  if (df.min_trend != null && df.min_trend > 0) params.min_trend = df.min_trend
  if (df.min_iv_vol != null && df.min_iv_vol > 0) params.min_iv_vol = df.min_iv_vol
  if (df.min_flow != null && df.min_flow > 0) params.min_flow = df.min_flow
  if (df.min_risk != null && df.min_risk > 0) params.min_risk = df.min_risk
  if (df.market_regime) params.market_regime = df.market_regime
  if (df.max_earnings_days !== undefined) params.max_earnings_days = df.max_earnings_days
  if (df.min_earnings_days !== undefined) params.min_earnings_days = df.min_earnings_days
  return params
}

function syncUrl(): void {
  const query: Record<string, string> = {}
  if (search.value) query.search = search.value
  if (direction.value) query.direction = direction.value
  if (sortField.value !== 'composite_score') query.sort = sortField.value
  if (sortOrder.value === 1) query.order = 'asc'
  if (page.value > 1) query.page = String(page.value)
  if (compareScanId.value !== null) query.compare = String(compareScanId.value)
  if (selectedSectorFilters.value.length > 0) query.sectors = selectedSectorFilters.value.join(',')
  if (selectedIndustryGroupFilters.value.length > 0) query.industry_groups = selectedIndustryGroupFilters.value.join(',')
  if (selectedThemeFilters.value.length > 0) query.themes = selectedThemeFilters.value.join(',')
  // Dimensional filter URL params (use > 0 to avoid falsy 0 suppression)
  const df = dimensionalFilters.value
  if (df.min_score != null && df.min_score > 0) query.min_score = String(df.min_score)
  if (df.min_confidence != null && df.min_confidence > 0) query.min_confidence = String(df.min_confidence)
  if (df.min_trend != null && df.min_trend > 0) query.min_trend = String(df.min_trend)
  if (df.min_iv_vol != null && df.min_iv_vol > 0) query.min_iv_vol = String(df.min_iv_vol)
  if (df.min_flow != null && df.min_flow > 0) query.min_flow = String(df.min_flow)
  if (df.min_risk != null && df.min_risk > 0) query.min_risk = String(df.min_risk)
  if (df.market_regime) query.market_regime = df.market_regime
  if (df.max_earnings_days !== undefined) query.max_earnings_days = String(df.max_earnings_days)
  if (df.min_earnings_days !== undefined) query.min_earnings_days = String(df.min_earnings_days)
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

/** Compute days to earnings from an ISO date string. */
function earningsDte(isoDate: string): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const earnings = new Date(isoDate + 'T00:00:00')
  const diffMs = earnings.getTime() - today.getTime()
  const days = Math.round(diffMs / (1000 * 60 * 60 * 24))
  return `${days}d`
}

/** Format direction_confidence as percentage string. */
function formatConfidence(val: number | null | undefined): string {
  if (val === null || val === undefined) return '--'
  return `${(val * 100).toFixed(0)}%`
}

/** CSS class for earnings DTE: red if < 7 days, gray otherwise. */
function earningsClass(isoDate: string): string {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const earnings = new Date(isoDate + 'T00:00:00')
  const diffMs = earnings.getTime() - today.getTime()
  const days = Math.round(diffMs / (1000 * 60 * 60 * 24))
  return days < 7 ? 'earnings-warn' : 'earnings-normal'
}

async function addToFirstWatchlist(ticker: string): Promise<void> {
  if (watchlistStore.watchlists.length === 0) {
    toast.add({
      severity: 'warn',
      summary: 'No Watchlists',
      detail: 'Create a watchlist first from the Watchlists page.',
      life: 5000,
    })
    return
  }
  const wl = watchlistStore.watchlists[0]
  const added = await watchlistStore.addTicker(wl.id, ticker)
  if (added) {
    toast.add({
      severity: 'success',
      summary: 'Added',
      detail: `${ticker} added to "${wl.name}".`,
      life: 3000,
    })
  } else {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: watchlistStore.error ?? 'Failed to add ticker',
      life: 5000,
    })
  }
}

onMounted(async () => {
  // Restore sector filters from URL
  const sectorsParam = route.query.sectors as string | undefined
  if (sectorsParam) {
    selectedSectorFilters.value = sectorsParam.split(',')
  }
  // Restore industry group filters from URL
  const igParam = route.query.industry_groups as string | undefined
  if (igParam) {
    selectedIndustryGroupFilters.value = igParam.split(',')
  }
  // Restore theme filters from URL
  const themesParam = route.query.themes as string | undefined
  if (themesParam) {
    selectedThemeFilters.value = themesParam.split(',')
  }
  // Restore dimensional filters from URL
  const restoredFilters: FilterParams = {}
  const q = route.query
  if (q.min_score) restoredFilters.min_score = Number(q.min_score)
  if (q.min_confidence) restoredFilters.min_confidence = Number(q.min_confidence)
  if (q.min_trend) restoredFilters.min_trend = Number(q.min_trend)
  if (q.min_iv_vol) restoredFilters.min_iv_vol = Number(q.min_iv_vol)
  if (q.min_flow) restoredFilters.min_flow = Number(q.min_flow)
  if (q.min_risk) restoredFilters.min_risk = Number(q.min_risk)
  if (q.market_regime) restoredFilters.market_regime = q.market_regime as FilterParams['market_regime']
  if (q.max_earnings_days) restoredFilters.max_earnings_days = Number(q.max_earnings_days)
  if (q.min_earnings_days) restoredFilters.min_earnings_days = Number(q.min_earnings_days)
  if (Object.keys(restoredFilters).length > 0) {
    dimensionalFilters.value = restoredFilters
  }
  await loadScores()
  void fetchSparklineData()
  void watchlistStore.fetchWatchlists()
  void fetchSectorOptions()
  void fetchThemeOptions()
  // Load scan list for compare dropdown
  await scanStore.fetchScans(20)
  // If compare param is in URL, fetch the diff
  if (compareScanId.value !== null) {
    void fetchDiff(compareScanId.value)
  }
})
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
      <span
        v-if="selectedSectorFilters.length > 0 || selectedIndustryGroupFilters.length > 0"
        class="active-sector-info"
        data-testid="active-sector-filter"
      >
        <template v-if="selectedSectorFilters.length > 0">
          Sectors: {{ selectedSectorFilters.join(', ') }}
        </template>
        <template v-if="selectedIndustryGroupFilters.length > 0">
          {{ selectedSectorFilters.length > 0 ? ' | ' : '' }}Groups: {{ selectedIndustryGroupFilters.join(', ') }}
        </template>
      </span>
      <span
        v-if="selectedThemeFilters.length > 0"
        class="active-theme-info"
        data-testid="active-theme-filter"
      >
        Themes: {{ selectedThemeFilters.join(', ') }}
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
      <SectorTree
        :sectors="sectorHierarchy"
        :selectedSectors="selectedSectorFilters"
        :selectedIndustryGroups="selectedIndustryGroupFilters"
        data-testid="sector-tree"
        @update:selectedSectors="(v: string[]) => { selectedSectorFilters = v; onSectorFilterChange() }"
        @update:selectedIndustryGroups="(v: string[]) => { selectedIndustryGroupFilters = v; onSectorFilterChange() }"
      />
      <Select
        v-model="compareScanId"
        :options="compareOptions"
        optionLabel="label"
        optionValue="value"
        placeholder="Compare with..."
        size="small"
        class="compare-select"
        data-testid="compare-select"
        :loading="diffLoading"
        @change="onCompareChange()"
      />
      <div class="batch-actions">
        <Button
          v-if="selectedTickers.length > 0"
          :label="`Debate Selected (${selectedTickers.length})`"
          icon="pi pi-comments"
          severity="success"
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
          outlined
          :disabled="anyBusy"
          data-testid="batch-debate-top5-btn"
          @click="onDebateTop5()"
        />
      </div>
    </div>

    <!-- Theme Filter Chips -->
    <ThemeChips
      :themes="availableThemes"
      :selectedThemes="selectedThemeFilters"
      @update:selectedThemes="onThemeFilterChange"
    />

    <!-- Top Movers Summary (shown when comparison is active) -->
    <Panel
      v-if="scanDiff && topMovers.length > 0"
      header="Top Movers"
      :toggleable="true"
      class="top-movers-panel"
      data-testid="top-movers-panel"
    >
      <div class="movers-grid">
        <div
          v-for="mover in topMovers"
          :key="mover.ticker"
          class="mover-item"
          :data-testid="`mover-${mover.ticker}`"
        >
          <span class="mover-ticker mono">{{ mover.ticker }}</span>
          <span v-if="mover.is_new">
            <Tag severity="success" value="NEW" data-testid="mover-new-tag" />
          </span>
          <span
            v-else
            class="mover-delta mono"
            :class="deltaClass(mover.score_change)"
            data-testid="mover-delta"
          >{{ formatDelta(mover.score_change) }}</span>
          <span class="mover-score mono">{{ mover.current_score.toFixed(1) }}</span>
        </div>
      </div>
      <div v-if="scanDiff.added.length > 0" class="movers-summary">
        <span class="summary-label">New tickers:</span>
        <span class="mono">{{ scanDiff.added.length }}</span>
      </div>
      <div v-if="scanDiff.removed.length > 0" class="movers-summary">
        <span class="summary-label">Removed:</span>
        <span class="mono">{{ scanDiff.removed.length }}</span>
      </div>
    </Panel>

    <!-- Filter Presets + Advanced Panel -->
    <FilterPresets
      :current-filters="dimensionalFilters"
      @preset-applied="onPresetApplied"
      @clear-all="onClearAllFilters"
    />
    <ScanFilterPanel
      v-model="dimensionalFilters"
      @update:model-value="onDimensionalFilterChange"
    />

    <!-- Regime Banner -->
    <RegimeBanner :scores="scanStore.scores" />

    <!-- Data Table -->
    <DataTable
      :value="scanStore.scores"
      :loading="scanStore.loading"
      dataKey="ticker"
      v-model:expandedRows="expandedRows"
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
      <Column expander :style="{ width: '3rem' }" />
      <Column field="ticker" header="Ticker" :sortable="true" :style="{ width: '120px' }">
        <template #body="{ data }">
          <span class="ticker-cell-wrapper">
            <span class="ticker-cell mono" data-testid="ticker-cell">{{ data.ticker }}</span>
            <Tag
              v-if="addedTickers.has(data.ticker)"
              severity="success"
              value="NEW"
              class="new-badge"
              data-testid="new-badge"
            />
          </span>
        </template>
      </Column>
      <Column field="sector" header="Sector" :sortable="true" :style="{ width: '160px' }">
        <template #body="{ data }">
          <Tag
            v-if="data.sector"
            :value="data.sector"
            :severity="sectorSeverity(data.sector)"
            class="sector-tag"
            :data-testid="`sector-${data.ticker}`"
          />
          <span v-else class="sector-none" :data-testid="`sector-${data.ticker}`">&mdash;</span>
        </template>
      </Column>
      <Column field="composite_score" header="Score" :sortable="true" :style="{ width: '120px' }">
        <template #body="{ data }">
          <span class="score-cell">
            <span class="mono" data-testid="composite-score">{{ data.composite_score.toFixed(1) }}</span>
            <span
              v-if="diffByTicker.has(data.ticker) && !diffByTicker.get(data.ticker)!.is_new"
              class="delta-chip mono"
              :class="deltaClass(diffByTicker.get(data.ticker)!.score_change)"
              data-testid="delta-chip"
            >{{ formatDelta(diffByTicker.get(data.ticker)!.score_change) }}</span>
          </span>
        </template>
      </Column>
      <Column field="direction" header="Direction" :sortable="true" :style="{ width: '110px' }">
        <template #body="{ data }">
          <DirectionBadge :direction="data.direction" />
        </template>
      </Column>
      <Column
        field="direction_confidence"
        header="Confidence"
        :sortable="true"
        :style="{ width: '100px' }"
      >
        <template #body="{ data }">
          <span class="mono" data-testid="direction-confidence">
            {{ formatConfidence(data.direction_confidence) }}
          </span>
        </template>
      </Column>
      <Column header="Trend" :style="{ width: '100px' }">
        <template #body="{ data }">
          <SparklineChart
            v-if="sparklineData.has(data.ticker)"
            :scores="sparklineData.get(data.ticker)!"
            :direction="(sparklineDirections.get(data.ticker) as 'bullish' | 'bearish' | 'neutral') ?? 'neutral'"
          />
          <span v-else class="sparkline-empty">&mdash;</span>
        </template>
      </Column>
      <Column field="next_earnings" header="Earnings" :sortable="true" :style="{ width: '90px' }">
        <template #body="{ data }">
          <span
            v-if="data.next_earnings"
            class="mono"
            :class="earningsClass(data.next_earnings)"
            :data-testid="`earnings-${data.ticker}`"
          >{{ earningsDte(data.next_earnings) }}</span>
          <span v-else class="earnings-none" :data-testid="`earnings-${data.ticker}`">&mdash;</span>
        </template>
      </Column>
      <Column header="" :style="{ width: '140px' }">
        <template #body="{ data }">
          <div class="row-actions">
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
            <Button
              icon="pi pi-bookmark"
              severity="secondary"
              size="small"
              text
              :data-testid="`watchlist-btn-${data.ticker}`"
              @click.stop="addToFirstWatchlist(data.ticker)"
            />
          </div>
        </template>
      </Column>
      <template #expansion="{ data }">
        <div class="expansion-content" data-testid="row-expansion">
          <DimensionalScoreBars :scores="data.dimensional_scores" />
        </div>
      </template>
      <template #empty>
        <div class="empty-msg" data-testid="empty-state">
          <i class="pi pi-search empty-icon" />
          <p class="empty-text">No results found matching your filters.</p>
        </div>
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

@media (max-width: 640px) {
  .filters {
    flex-direction: column;
    align-items: stretch;
  }

  .search-input {
    min-width: unset;
    width: 100%;
  }

  .compare-select {
    min-width: unset;
    width: 100%;
  }

  .batch-actions {
    margin-left: 0;
  }
}

.search-input {
  min-width: 200px;
}

.compare-select {
  min-width: 220px;
}

.sector-filter {
  min-width: 220px;
  max-width: 400px;
}

.active-sector-info {
  font-size: 0.8rem;
  color: var(--accent-blue, #3b82f6);
  margin-left: auto;
}

.active-theme-info {
  font-size: 0.8rem;
  color: var(--accent-purple, #a855f7);
}

.sector-tag {
  font-size: 0.7rem;
  white-space: nowrap;
}

.sector-none {
  color: var(--p-surface-500, #666);
}

.batch-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

/* Top movers panel */
.top-movers-panel {
  margin-bottom: 1rem;
}

.movers-grid {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.mover-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}

.mover-ticker {
  font-weight: 600;
  min-width: 50px;
}

.mover-score {
  color: var(--p-surface-400, #888);
  font-size: 0.85rem;
}

.mover-delta {
  font-size: 0.85rem;
  font-weight: 600;
}

.movers-summary {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  margin-top: 0.25rem;
}

.summary-label {
  font-weight: 500;
}

/* Table styles */
.results-table :deep(tr) {
  cursor: pointer;
}

.results-table :deep(tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.ticker-cell-wrapper {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.ticker-cell {
  font-weight: 600;
}

.new-badge {
  font-size: 0.65rem;
}

.score-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.delta-chip {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
}

.delta-positive {
  color: var(--accent-green, #22c55e);
  background: rgba(34, 197, 94, 0.15);
}

.delta-negative {
  color: var(--accent-red, #ef4444);
  background: rgba(239, 68, 68, 0.15);
}

.delta-neutral {
  color: var(--p-surface-400, #888);
  background: rgba(136, 136, 136, 0.1);
}

.mono {
  font-family: var(--font-mono);
}

.row-actions {
  display: flex;
  gap: 0.25rem;
  align-items: center;
}

.empty-msg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0;
  font-size: 0.9rem;
}

.earnings-warn {
  color: var(--accent-red, #ef4444);
  font-weight: 600;
}

.earnings-normal {
  color: var(--p-surface-400, #888);
}

.earnings-none {
  color: var(--p-surface-500, #666);
}

.sparkline-empty {
  color: var(--p-surface-500, #666);
  font-size: 0.8rem;
}

.expansion-content {
  padding: 0.75rem 1.5rem;
  max-width: 400px;
}
</style>
