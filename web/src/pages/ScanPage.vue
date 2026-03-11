<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Badge from 'primevue/badge'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressTracker from '@/components/ProgressTracker.vue'
import PreScanFilters from '@/components/scan/PreScanFilters.vue'
import FilterSummaryChips from '@/components/scan/FilterSummaryChips.vue'
import { useScanStore } from '@/stores/scan'
import { useOperationStore } from '@/stores/operation'
import { useWebSocket } from '@/composables/useWebSocket'
import { ApiError } from '@/composables/useApi'
import { formatScanDuration, formatDateTime } from '@/utils/formatters'
import type { ScanEvent } from '@/types/ws'
import type { PreScanFilterPayload, ScanRun } from '@/types'

const router = useRouter()
const toast = useToast()
const scanStore = useScanStore()
const opStore = useOperationStore()

const SCAN_PHASES = ['universe', 'scoring', 'options', 'persist']

// Template ref for programmatic filter clearing
const preFiltersRef = ref<InstanceType<typeof PreScanFilters> | null>(null)

// Current filter state from PreScanFilters component
const currentFilters = ref<PreScanFilterPayload>({ preset: 'sp500' })

function onFiltersUpdate(payload: PreScanFilterPayload): void {
  currentFilters.value = payload
}

function handleClearFilter(key: string): void {
  preFiltersRef.value?.clearFilter(key)
}

function handleClearAll(): void {
  preFiltersRef.value?.clearAll()
}

// WebSocket connection for live scan progress
let wsClose: (() => void) | null = null

async function runScan(): Promise<void> {
  try {
    opStore.start('scan')
    const f = currentFilters.value
    const scanId = await scanStore.startScan({
      preset: f.preset ?? 'sp500',
      sectors: f.sectors,
      industryGroups: f.industryGroups,
      customTickers: f.custom_tickers,
      market_cap_tiers: f.market_cap_tiers,
      exclude_near_earnings_days: f.exclude_near_earnings_days,
      direction_filter: f.direction_filter,
      min_iv_rank: f.min_iv_rank,
      min_price: f.min_price,
      max_price: f.max_price,
      min_dte: f.min_dte,
      max_dte: f.max_dte,
      min_score: f.min_score,
      min_direction_confidence: f.min_direction_confidence,
      top_n: f.top_n,
      min_dollar_volume: f.min_dollar_volume,
      min_oi: f.min_oi,
      min_volume: f.min_volume,
      max_spread_pct: f.max_spread_pct,
      delta_primary_min: f.delta_primary_min,
      delta_primary_max: f.delta_primary_max,
      delta_fallback_min: f.delta_fallback_min,
      delta_fallback_max: f.delta_fallback_max,
    })

    // Connect to WebSocket for progress updates
    const { close } = useWebSocket<ScanEvent>({
      url: `/ws/scan/${scanId}`,
      onMessage(event) {
        switch (event.type) {
          case 'progress':
            scanStore.updateProgress(event)
            break
          case 'error':
            scanStore.addError(event)
            toast.add({ severity: 'warn', summary: 'Scan Warning', detail: event.message, life: 5000 })
            break
          case 'complete':
            scanStore.setComplete(event)
            opStore.finish()
            close()  // Stop reconnection — terminal event
            if (event.cancelled) {
              toast.add({ severity: 'info', summary: 'Scan Cancelled', life: 3000 })
            } else {
              const detail = event.outcomes_collected > 0
                ? `Scan #${event.scan_id} finished — ${event.outcomes_collected} outcomes collected`
                : `Scan #${event.scan_id} finished`
              toast.add({ severity: 'success', summary: 'Scan Complete', detail, life: 5000 })
              void scanStore.fetchScans()
            }
            break
        }
      },
    })
    wsClose = close
  } catch (e) {
    opStore.finish()
    scanStore.reset()
    const msg = e instanceof ApiError ? e.message : 'Failed to start scan'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

async function handleCancel(): Promise<void> {
  try {
    await scanStore.cancelScan()
    toast.add({ severity: 'info', summary: 'Cancelling...', detail: 'Scan cancellation requested', life: 3000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Error', detail: 'Failed to cancel scan', life: 5000 })
  }
}

function viewResults(scanId: number): void {
  router.push(`/scan/${scanId}`)
}

onMounted(() => {
  void scanStore.fetchScans()
})
onUnmounted(() => {
  wsClose?.()
  if (opStore.inProgress) opStore.finish()
})
</script>

<template>
  <div class="page">
    <!-- Page header with subtitle -->
    <div class="page-header">
      <h1 data-testid="scan-title">Scan</h1>
      <p class="page-subtitle">Configure and launch options universe scans</p>
    </div>

    <!-- Pre-scan Filters -->
    <PreScanFilters
      ref="preFiltersRef"
      :disabled="scanStore.isScanning || opStore.inProgress"
      @update:filters="onFiltersUpdate"
    />

    <!-- Filter Summary + Launch -->
    <div v-if="!scanStore.isScanning" class="launch-section">
      <FilterSummaryChips
        :filters="currentFilters"
        :sector-count="currentFilters.sectors?.length ?? 0"
        :industry-group-count="currentFilters.industryGroups?.length ?? 0"
        :disabled="opStore.inProgress"
        @clear-filter="handleClearFilter"
        @clear-all="handleClearAll"
      />
      <Button
        label="Run Scan"
        icon="pi pi-play"
        severity="success"
        size="large"
        :disabled="scanStore.isScanning || opStore.inProgress"
        :loading="scanStore.isScanning"
        data-testid="start-scan-btn"
        @click="runScan()"
      />
    </div>

    <!-- Progress (replaces launch when scanning) -->
    <ProgressTracker
      v-if="scanStore.isScanning && scanStore.progress"
      :phases="SCAN_PHASES"
      :current-phase="scanStore.progress.phase"
      :current="scanStore.progress.current"
      :total="scanStore.progress.total"
      class="progress-panel"
      @cancel="handleCancel()"
    />

    <!-- Past Scans -->
    <section class="section past-scans-section">
      <h2>
        Past Scans
        <Badge v-if="scanStore.scans.length > 0" :value="String(scanStore.scans.length)" severity="secondary" />
      </h2>
      <DataTable
        :value="scanStore.scans"
        :loading="scanStore.loading && !scanStore.isScanning"
        dataKey="id"
        :rows="10"
        responsiveLayout="scroll"
        class="scans-table"
        data-testid="scan-list-table"
        @row-click="(e: { data: { id: number } }) => viewResults(e.data.id)"
      >
        <Column header="ID" field="id" :style="{ width: '60px' }">
          <template #body="{ data }">
            <span class="mono">#{{ data.id }}</span>
          </template>
        </Column>
        <Column header="Preset" field="preset">
          <template #body="{ data }">
            <span class="preset-tag">{{ (data.preset as string).toUpperCase() }}</span>
          </template>
        </Column>
        <Column header="Scanned" field="tickers_scanned">
          <template #body="{ data }">
            <span class="mono">{{ data.tickers_scanned.toLocaleString() }}</span>
          </template>
        </Column>
        <Column header="Scored" field="tickers_scored">
          <template #body="{ data }">
            <span class="mono">{{ data.tickers_scored.toLocaleString() }}</span>
          </template>
        </Column>
        <Column header="Recs" field="recommendations">
          <template #body="{ data }">
            <span class="mono">{{ data.recommendations }}</span>
          </template>
        </Column>
        <Column header="Date" field="started_at">
          <template #body="{ data }">{{ formatDateTime(data.started_at) }}</template>
        </Column>
        <Column header="Duration" :style="{ width: '90px' }">
          <template #body="{ data }">
            <span class="mono">{{ formatScanDuration(data as ScanRun) }}</span>
          </template>
        </Column>
        <template #empty>
          <div class="empty-msg" data-testid="scan-list-empty">No scans yet. Run your first scan above.</div>
        </template>
      </DataTable>
    </section>
  </div>
</template>

<style scoped>
.page-header {
  margin-bottom: 1.5rem;
}

.page-subtitle {
  color: var(--p-surface-400, #888);
  font-size: 0.9rem;
  margin: 0.25rem 0 0;
}

.launch-section {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  margin: 1rem 0;
}

.progress-panel {
  margin-bottom: 1.5rem;
}

.section {
  margin-top: 1rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.scans-table :deep(tr) {
  cursor: pointer;
  transition: background-color 0.15s;
}

.scans-table :deep(tbody tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.mono {
  font-family: var(--font-mono);
}

.preset-tag {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-green);
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}
</style>
