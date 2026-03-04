<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import { useConfirm } from 'primevue/useconfirm'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Select from 'primevue/select'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import ConfirmDialog from 'primevue/confirmdialog'
import DirectionBadge from '@/components/DirectionBadge.vue'
import { useWatchlistStore } from '@/stores/watchlist'
import type { WatchlistTicker } from '@/types'

const router = useRouter()
const toast = useToast()
const confirm = useConfirm()
const watchlistStore = useWatchlistStore()

const selectedWatchlistId = ref<number | null>(null)
const showCreateDialog = ref(false)
const newWatchlistName = ref('')
const creating = ref(false)
const newTicker = ref('')
const addingTicker = ref(false)

// Load watchlists on mount
onMounted(async () => {
  await watchlistStore.fetchWatchlists()
  // Auto-select first watchlist if available
  if (watchlistStore.watchlists.length > 0) {
    selectedWatchlistId.value = watchlistStore.watchlists[0].id
  }
})

// Fetch detail when selected watchlist changes
watch(selectedWatchlistId, async (id) => {
  if (id !== null) {
    await watchlistStore.fetchWatchlistDetail(id)
  } else {
    watchlistStore.activeWatchlist = null
  }
})

// Build options for the watchlist selector
function watchlistOptions(): Array<{ label: string; value: number }> {
  return watchlistStore.watchlists.map((w) => ({
    label: `${w.name} (${w.id})`,
    value: w.id,
  }))
}

async function onCreateWatchlist(): Promise<void> {
  const name = newWatchlistName.value.trim()
  if (!name) return

  creating.value = true
  const result = await watchlistStore.createWatchlist(name)
  creating.value = false

  if (result) {
    toast.add({
      severity: 'success',
      summary: 'Watchlist Created',
      detail: `"${result.name}" created successfully.`,
      life: 5000,
    })
    showCreateDialog.value = false
    newWatchlistName.value = ''
    selectedWatchlistId.value = result.id
  } else {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: watchlistStore.error ?? 'Failed to create watchlist',
      life: 5000,
    })
  }
}

function onDeleteWatchlist(): void {
  if (selectedWatchlistId.value === null) return
  const wl = watchlistStore.watchlists.find((w) => w.id === selectedWatchlistId.value)
  if (!wl) return

  confirm.require({
    message: `Delete watchlist "${wl.name}"? This cannot be undone.`,
    header: 'Delete Watchlist',
    acceptClass: 'p-button-danger',
    accept: async () => {
      const deleted = await watchlistStore.deleteWatchlist(wl.id)
      if (deleted) {
        toast.add({
          severity: 'success',
          summary: 'Deleted',
          detail: `"${wl.name}" deleted.`,
          life: 5000,
        })
        // Select next available or null
        selectedWatchlistId.value =
          watchlistStore.watchlists.length > 0 ? watchlistStore.watchlists[0].id : null
      } else {
        toast.add({
          severity: 'error',
          summary: 'Error',
          detail: watchlistStore.error ?? 'Failed to delete watchlist',
          life: 5000,
        })
      }
    },
  })
}

async function onAddTicker(): Promise<void> {
  const ticker = newTicker.value.trim().toUpperCase()
  if (!ticker || selectedWatchlistId.value === null) return

  addingTicker.value = true
  const success = await watchlistStore.addTicker(selectedWatchlistId.value, ticker)
  addingTicker.value = false

  if (success) {
    toast.add({
      severity: 'success',
      summary: 'Ticker Added',
      detail: `${ticker} added to watchlist.`,
      life: 5000,
    })
    newTicker.value = ''
  } else {
    toast.add({
      severity: 'error',
      summary: 'Error',
      detail: watchlistStore.error ?? `Failed to add ${ticker}`,
      life: 5000,
    })
  }
}

async function onRemoveTicker(ticker: string): Promise<void> {
  if (selectedWatchlistId.value === null) return
  const removed = await watchlistStore.removeTicker(selectedWatchlistId.value, ticker)
  if (removed) {
    toast.add({
      severity: 'info',
      summary: 'Removed',
      detail: `${ticker} removed from watchlist.`,
      life: 5000,
    })
  }
}

function onRowClick(event: { data: WatchlistTicker }): void {
  void router.push(`/ticker/${event.data.ticker}`)
}

function formatRelativeDate(iso: string | null): string {
  if (!iso) return '--'
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  if (diffHours < 1) return 'Just now'
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function scoreClass(score: number | null): string {
  if (score === null) return ''
  if (score >= 7) return 'score-high'
  if (score >= 4) return 'score-mid'
  return 'score-low'
}
</script>

<template>
  <div class="page">
    <ConfirmDialog />

    <div class="page-header">
      <h1>Watchlists</h1>
    </div>

    <!-- Empty state: no watchlists exist -->
    <div
      v-if="!watchlistStore.loading && watchlistStore.watchlists.length === 0"
      class="empty-state"
      data-testid="watchlist-empty-state"
    >
      <p class="empty-title">Create your first watchlist</p>
      <p class="empty-msg">Track tickers you want to monitor across scans and debates.</p>
      <Button
        label="Create Watchlist"
        icon="pi pi-plus"
        severity="success"
        data-testid="create-watchlist-empty-btn"
        @click="showCreateDialog = true"
      />
    </div>

    <!-- Watchlist controls -->
    <div v-else class="watchlist-controls">
      <Select
        v-model="selectedWatchlistId"
        :options="watchlistOptions()"
        optionLabel="label"
        optionValue="value"
        placeholder="Select watchlist"
        data-testid="watchlist-selector"
        class="watchlist-select"
      />
      <Button
        label="Create"
        icon="pi pi-plus"
        severity="success"
        size="small"
        data-testid="create-watchlist-btn"
        @click="showCreateDialog = true"
      />
      <Button
        label="Delete"
        icon="pi pi-trash"
        severity="danger"
        size="small"
        :disabled="selectedWatchlistId === null"
        data-testid="delete-watchlist-btn"
        @click="onDeleteWatchlist()"
      />
    </div>

    <!-- Add ticker input -->
    <div v-if="selectedWatchlistId !== null" class="ticker-input-row">
      <InputText
        v-model="newTicker"
        placeholder="e.g. AAPL"
        class="ticker-input"
        data-testid="add-ticker-input"
        @keydown.enter="onAddTicker"
      />
      <Button
        label="Add"
        icon="pi pi-plus"
        size="small"
        :loading="addingTicker"
        :disabled="!newTicker.trim() || addingTicker"
        data-testid="add-ticker-btn"
        @click="onAddTicker"
      />
    </div>

    <!-- Watchlist tickers table -->
    <div v-if="watchlistStore.activeWatchlist" class="watchlist-detail">
      <DataTable
        :value="watchlistStore.activeWatchlist.tickers"
        :loading="watchlistStore.loading"
        dataKey="ticker"
        sortMode="single"
        sortField="ticker"
        :sortOrder="1"
        @row-click="onRowClick"
        class="watchlist-table"
        data-testid="watchlist-table"
      >
        <Column field="ticker" header="Ticker" :sortable="true" :style="{ width: '100px' }">
          <template #body="{ data }">
            <span class="ticker-cell mono" data-testid="watchlist-ticker">{{ data.ticker }}</span>
          </template>
        </Column>
        <Column
          field="composite_score"
          header="Score"
          :sortable="true"
          :style="{ width: '80px' }"
        >
          <template #body="{ data }">
            <span
              v-if="data.composite_score !== null"
              class="mono"
              :class="scoreClass(data.composite_score)"
              data-testid="watchlist-score"
            >
              {{ data.composite_score.toFixed(1) }}
            </span>
            <span v-else class="muted">--</span>
          </template>
        </Column>
        <Column field="direction" header="Direction" :sortable="true" :style="{ width: '110px' }">
          <template #body="{ data }">
            <DirectionBadge
              v-if="data.direction"
              :direction="data.direction as 'bullish' | 'bearish' | 'neutral'"
            />
            <span v-else class="muted">--</span>
          </template>
        </Column>
        <Column field="last_debate_at" header="Last Debate" :sortable="true">
          <template #body="{ data }">
            <span class="debate-date">{{ formatRelativeDate(data.last_debate_at) }}</span>
          </template>
        </Column>
        <Column header="" :style="{ width: '80px' }">
          <template #body="{ data }">
            <Button
              icon="pi pi-times"
              severity="danger"
              size="small"
              text
              :data-testid="`remove-ticker-${data.ticker}`"
              @click.stop="onRemoveTicker(data.ticker)"
            />
          </template>
        </Column>
        <template #empty>
          <div class="empty-msg" data-testid="watchlist-tickers-empty">
            No tickers yet. Use the input above or add from scan results.
          </div>
        </template>
      </DataTable>
    </div>

    <!-- Create Watchlist Dialog -->
    <Dialog
      v-model:visible="showCreateDialog"
      header="Create Watchlist"
      :modal="true"
      :style="{ width: '400px' }"
      data-testid="create-watchlist-dialog"
    >
      <div class="create-form">
        <label for="watchlist-name" class="create-label">Name</label>
        <InputText
          id="watchlist-name"
          v-model="newWatchlistName"
          placeholder="e.g. Tech Watchlist"
          class="create-input"
          data-testid="watchlist-name-input"
          @keydown.enter="onCreateWatchlist"
        />
      </div>
      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          size="small"
          @click="showCreateDialog = false"
        />
        <Button
          label="Create"
          icon="pi pi-check"
          severity="success"
          size="small"
          :loading="creating"
          :disabled="!newWatchlistName.trim()"
          data-testid="confirm-create-btn"
          @click="onCreateWatchlist"
        />
      </template>
    </Dialog>
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

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem;
  text-align: center;
}

.empty-title {
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--p-surface-200, #ccc);
}

.empty-msg {
  color: var(--p-surface-400, #888);
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

.watchlist-controls {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
  align-items: center;
  flex-wrap: wrap;
}

.watchlist-select {
  min-width: 250px;
}

.ticker-input-row {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
  align-items: center;
}

.ticker-input {
  width: 160px;
  text-transform: uppercase;
}

.watchlist-detail {
  margin-top: 0.5rem;
}

.watchlist-table :deep(tr) {
  cursor: pointer;
}

.watchlist-table :deep(tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.ticker-cell {
  font-weight: 600;
}

.mono {
  font-family: var(--font-mono);
}

.muted {
  color: var(--p-surface-500, #666);
  font-size: 0.85rem;
}

.debate-date {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

.score-high {
  color: var(--accent-green);
}

.score-mid {
  color: var(--accent-yellow);
}

.score-low {
  color: var(--accent-red);
}

.create-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.create-label {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
}

.create-input {
  width: 100%;
}
</style>
