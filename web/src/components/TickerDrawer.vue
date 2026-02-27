<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Drawer from 'primevue/drawer'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Select from 'primevue/select'
import DirectionBadge from './DirectionBadge.vue'
import { api, ApiError } from '@/composables/useApi'
import { useWatchlistStore } from '@/stores/watchlist'
import type { TickerScore, DebateResultSummary } from '@/types'

interface Props {
  visible: boolean
  score: TickerScore | null
  scanId: number
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:visible': [value: boolean] }>()
const router = useRouter()
const toast = useToast()
const watchlistStore = useWatchlistStore()

const debates = ref<DebateResultSummary[]>([])
const loadingDebates = ref(false)
const watchlistDialogVisible = ref(false)
const selectedWatchlistId = ref<number | null>(null)
const addingToWatchlist = ref(false)

watch(
  () => props.score?.ticker,
  async (ticker) => {
    if (!ticker) {
      debates.value = []
      return
    }
    loadingDebates.value = true
    try {
      debates.value = await api<DebateResultSummary[]>('/api/debate', {
        params: { ticker, limit: 5 },
      })
    } catch {
      debates.value = []
    } finally {
      loadingDebates.value = false
    }
  },
)

/** Format signal names for display: rsi → RSI, bb_width → BB Width */
function formatSignalName(key: string): string {
  return key
    .split('_')
    .map((w) => w.toUpperCase())
    .join(' ')
}

function formatSignalValue(val: number | null): string {
  if (val === null) return '--'
  return val.toFixed(2)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

function openWatchlistDialog(): void {
  selectedWatchlistId.value = null
  watchlistDialogVisible.value = true
}

async function handleAddToWatchlist(): Promise<void> {
  if (!selectedWatchlistId.value || !props.score) return

  addingToWatchlist.value = true
  try {
    await watchlistStore.addTicker(selectedWatchlistId.value, props.score.ticker)
    watchlistDialogVisible.value = false
    toast.add({
      severity: 'success',
      summary: 'Added',
      detail: `${props.score.ticker} added to watchlist`,
      life: 3000,
    })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to add ticker to watchlist'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  } finally {
    addingToWatchlist.value = false
  }
}

onMounted(() => void watchlistStore.fetchWatchlists())
</script>

<template>
  <Drawer
    :visible="visible"
    position="right"
    :header="score?.ticker ?? 'Ticker Detail'"
    :style="{ width: '400px' }"
    data-testid="ticker-drawer"
    @update:visible="emit('update:visible', $event)"
  >
    <template v-if="score">
      <div class="drawer-section">
        <h3>Score</h3>
        <div class="score-row">
          <span class="score-value mono">{{ score.composite_score.toFixed(1) }}</span>
          <DirectionBadge :direction="score.direction" />
        </div>
      </div>

      <div class="drawer-section">
        <h3>Indicators</h3>
        <div class="signal-grid">
          <div
            v-for="(val, key) in score.signals"
            :key="key"
            class="signal-row"
          >
            <span class="signal-name">{{ formatSignalName(String(key)) }}</span>
            <span class="signal-value mono">{{ formatSignalValue(val as number | null) }}</span>
          </div>
        </div>
      </div>

      <div class="drawer-section">
        <h3>Past Debates</h3>
        <div v-if="loadingDebates" class="muted">Loading...</div>
        <div v-else-if="debates.length === 0" class="muted">No debates for this ticker.</div>
        <div v-else class="debate-list">
          <div
            v-for="d in debates"
            :key="d.id"
            class="debate-item"
            @click="router.push(`/debate/${d.id}`)"
          >
            <DirectionBadge :direction="d.direction as 'bullish' | 'bearish' | 'neutral'" />
            <span class="mono">{{ (d.confidence * 100).toFixed(0) }}%</span>
            <span class="debate-date">{{ formatDate(d.created_at) }}</span>
          </div>
        </div>
      </div>

      <div class="drawer-actions">
        <Button
          label="Debate This Ticker"
          icon="pi pi-comments"
          severity="info"
          size="small"
          disabled
        />
        <Button
          label="Add to Watchlist"
          icon="pi pi-bookmark"
          severity="secondary"
          size="small"
          data-testid="add-to-watchlist-btn"
          @click="openWatchlistDialog()"
        />
      </div>
    </template>
  </Drawer>

  <!-- Add to Watchlist Dialog -->
  <Dialog
    v-model:visible="watchlistDialogVisible"
    header="Add to Watchlist"
    :style="{ width: '350px' }"
    modal
    data-testid="add-to-watchlist-dialog"
  >
    <div class="watchlist-select-form">
      <p class="watchlist-select-label">
        Add <strong>{{ score?.ticker }}</strong> to:
      </p>
      <Select
        v-model="selectedWatchlistId"
        :options="watchlistStore.watchlists.map(w => ({ label: w.name, value: w.id }))"
        optionLabel="label"
        optionValue="value"
        placeholder="Select a watchlist"
        class="full-width"
        data-testid="watchlist-picker"
      />
      <div v-if="watchlistStore.watchlists.length === 0" class="no-watchlists-msg">
        No watchlists found. Create one on the Watchlists page first.
      </div>
    </div>
    <template #footer>
      <Button
        label="Cancel"
        severity="secondary"
        text
        @click="watchlistDialogVisible = false"
      />
      <Button
        label="Add"
        icon="pi pi-plus"
        :loading="addingToWatchlist"
        :disabled="!selectedWatchlistId"
        data-testid="confirm-add-to-watchlist-btn"
        @click="handleAddToWatchlist()"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.drawer-section {
  margin-bottom: 1.25rem;
}

.drawer-section h3 {
  font-size: 0.9rem;
  margin: 0 0 0.5rem 0;
  color: var(--p-surface-300, #aaa);
}

.score-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.score-value {
  font-size: 1.5rem;
  font-weight: 700;
}

.signal-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.25rem 1rem;
}

.signal-row {
  display: contents;
}

.signal-name {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.signal-value {
  font-size: 0.8rem;
  text-align: right;
}

.debate-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.debate-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.8rem;
}

.debate-item:hover {
  background: var(--p-surface-700, #333);
}

.debate-date {
  margin-left: auto;
  color: var(--p-surface-500, #666);
  font-size: 0.75rem;
}

.muted {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}

.mono {
  font-family: var(--font-mono);
}

.drawer-actions {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--p-surface-700, #333);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.watchlist-select-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.watchlist-select-label {
  margin: 0;
  font-size: 0.9rem;
}

.full-width {
  width: 100%;
}

.no-watchlists-msg {
  font-size: 0.85rem;
  color: var(--p-surface-500, #666);
}
</style>
