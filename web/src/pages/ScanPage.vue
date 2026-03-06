<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressTracker from '@/components/ProgressTracker.vue'
import PreScanFilters from '@/components/scan/PreScanFilters.vue'
import { useScanStore } from '@/stores/scan'
import { useOperationStore } from '@/stores/operation'
import { useWebSocket } from '@/composables/useWebSocket'
import { ApiError } from '@/composables/useApi'
import type { ScanEvent } from '@/types/ws'
import type { PreScanFilterPayload, ScanRun } from '@/types'

const router = useRouter()
const toast = useToast()
const scanStore = useScanStore()
const opStore = useOperationStore()

const SCAN_PHASES = ['universe', 'scoring', 'options', 'persist']

// Current filter state from PreScanFilters component
const currentFilters = ref<PreScanFilterPayload>({ preset: 'sp500' })

function onFiltersUpdate(payload: PreScanFilterPayload): void {
  currentFilters.value = payload
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
      themes: f.themes,
      market_cap_tiers: f.market_cap_tiers,
      exclude_near_earnings_days: f.exclude_near_earnings_days,
      direction_filter: f.direction_filter,
      min_iv_rank: f.min_iv_rank,
      min_price: f.min_price,
      max_price: f.max_price,
      min_dte: f.min_dte,
      max_dte: f.max_dte,
      min_score: f.min_score,
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
              toast.add({ severity: 'success', summary: 'Scan Complete', detail: `Scan #${event.scan_id} finished`, life: 5000 })
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

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function formatScanDuration(scan: ScanRun): string {
  if (!scan.completed_at || !scan.started_at) return '--'
  const ms = new Date(scan.completed_at).getTime() - new Date(scan.started_at).getTime()
  if (ms < 0) return '--'
  const totalSec = Math.round(ms / 1000)
  if (totalSec < 60) return `${totalSec}s`
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`
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
    <h1 data-testid="scan-title">Scan</h1>

    <!-- Pre-scan Filters -->
    <PreScanFilters
      :disabled="scanStore.isScanning || opStore.inProgress"
      @update:filters="onFiltersUpdate"
    />

    <!-- Run Scan Button -->
    <div class="launch-panel">
      <Button
        label="Run Scan"
        icon="pi pi-play"
        severity="success"
        :disabled="scanStore.isScanning || opStore.inProgress"
        :loading="scanStore.isScanning"
        data-testid="start-scan-btn"
        @click="runScan()"
      />
    </div>

    <!-- Progress Panel -->
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
    <section class="section">
      <h2>Past Scans</h2>
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
            <span v-if="data.source === 'watchlist'" class="source-tag">WL</span>
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
          <template #body="{ data }">{{ formatDate(data.started_at) }}</template>
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
.launch-panel {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
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

.source-tag {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--accent-blue);
  margin-left: 0.4rem;
  padding: 0.1rem 0.3rem;
  border: 1px solid var(--accent-blue);
  border-radius: 0.25rem;
  vertical-align: middle;
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}
</style>
