<script setup lang="ts">
import { ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Dialog from 'primevue/dialog'
import Textarea from 'primevue/textarea'
import { useWatchlistStore } from '@/stores/watchlist'
import { ApiError } from '@/composables/useApi'

interface Props {
  watchlistId: number
}

const props = defineProps<Props>()
const toast = useToast()
const store = useWatchlistStore()

const newTicker = ref('')
const addingTicker = ref(false)
const editDialogVisible = ref(false)
const editName = ref('')
const editDescription = ref('')

// Load watchlist detail when id changes
watch(
  () => props.watchlistId,
  async (id) => {
    if (id) {
      await store.fetchWatchlist(id)
      if (store.currentWatchlist) {
        editName.value = store.currentWatchlist.name
        editDescription.value = store.currentWatchlist.description ?? ''
      }
    }
  },
  { immediate: true },
)

async function handleAddTicker(): Promise<void> {
  const ticker = newTicker.value.trim().toUpperCase()
  if (!ticker) return

  addingTicker.value = true
  try {
    await store.addTicker(props.watchlistId, ticker)
    newTicker.value = ''
    toast.add({ severity: 'success', summary: 'Ticker Added', detail: `${ticker} added to watchlist`, life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to add ticker'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  } finally {
    addingTicker.value = false
  }
}

async function handleRemoveTicker(ticker: string): Promise<void> {
  try {
    await store.removeTicker(props.watchlistId, ticker)
    toast.add({ severity: 'success', summary: 'Ticker Removed', detail: `${ticker} removed from watchlist`, life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to remove ticker'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

function openEditDialog(): void {
  if (store.currentWatchlist) {
    editName.value = store.currentWatchlist.name
    editDescription.value = store.currentWatchlist.description ?? ''
    editDialogVisible.value = true
  }
}

async function handleSaveEdit(): Promise<void> {
  try {
    await store.updateWatchlist(props.watchlistId, {
      name: editName.value.trim(),
      description: editDescription.value.trim() || undefined,
    })
    editDialogVisible.value = false
    toast.add({ severity: 'success', summary: 'Updated', detail: 'Watchlist updated', life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to update watchlist'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <div class="watchlist-manager" data-testid="watchlist-manager">
    <div v-if="store.loading && !store.currentWatchlist" class="loading-msg">Loading...</div>

    <template v-else-if="store.currentWatchlist">
      <!-- Header -->
      <div class="manager-header">
        <div class="header-info">
          <h2>{{ store.currentWatchlist.name }}</h2>
          <p v-if="store.currentWatchlist.description" class="description">
            {{ store.currentWatchlist.description }}
          </p>
        </div>
        <Button
          icon="pi pi-pencil"
          severity="secondary"
          text
          rounded
          size="small"
          aria-label="Edit watchlist"
          data-testid="edit-watchlist-btn"
          @click="openEditDialog()"
        />
      </div>

      <!-- Add Ticker -->
      <div class="add-ticker-row">
        <InputText
          v-model="newTicker"
          placeholder="Enter ticker symbol (e.g. AAPL)"
          :disabled="addingTicker"
          data-testid="add-ticker-input"
          @keyup.enter="handleAddTicker()"
        />
        <Button
          label="Add"
          icon="pi pi-plus"
          severity="success"
          size="small"
          :loading="addingTicker"
          :disabled="!newTicker.trim()"
          data-testid="add-ticker-btn"
          @click="handleAddTicker()"
        />
      </div>

      <!-- Tickers Table -->
      <DataTable
        :value="store.currentWatchlist.tickers"
        dataKey="id"
        :rows="50"
        responsiveLayout="scroll"
        class="tickers-table"
        data-testid="watchlist-tickers-table"
      >
        <Column header="Ticker" field="ticker" :style="{ width: '40%' }">
          <template #body="{ data }">
            <span class="ticker-symbol mono">{{ data.ticker }}</span>
          </template>
        </Column>
        <Column header="Added" field="added_at">
          <template #body="{ data }">
            <span class="date-text">{{ formatDate(data.added_at) }}</span>
          </template>
        </Column>
        <Column header="" :style="{ width: '80px', textAlign: 'center' }">
          <template #body="{ data }">
            <Button
              icon="pi pi-trash"
              severity="danger"
              text
              rounded
              size="small"
              :aria-label="`Remove ${data.ticker}`"
              :data-testid="`remove-ticker-${data.ticker}`"
              @click="handleRemoveTicker(data.ticker)"
            />
          </template>
        </Column>
        <template #empty>
          <div class="empty-msg" data-testid="tickers-empty">
            No tickers yet. Add your first ticker above.
          </div>
        </template>
      </DataTable>
    </template>

    <!-- Edit Dialog -->
    <Dialog
      v-model:visible="editDialogVisible"
      header="Edit Watchlist"
      :style="{ width: '400px' }"
      modal
      data-testid="edit-watchlist-dialog"
    >
      <div class="dialog-form">
        <label for="edit-name">Name</label>
        <InputText
          id="edit-name"
          v-model="editName"
          class="full-width"
          data-testid="edit-watchlist-name"
        />
        <label for="edit-desc">Description</label>
        <Textarea
          id="edit-desc"
          v-model="editDescription"
          rows="3"
          class="full-width"
          data-testid="edit-watchlist-description"
        />
      </div>
      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          @click="editDialogVisible = false"
        />
        <Button
          label="Save"
          icon="pi pi-check"
          :disabled="!editName.trim()"
          data-testid="save-edit-btn"
          @click="handleSaveEdit()"
        />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.watchlist-manager {
  margin-top: 0.5rem;
}

.manager-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.manager-header h2 {
  margin: 0;
  font-size: 1.25rem;
}

.description {
  margin: 0.25rem 0 0 0;
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

.add-ticker-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 1rem;
}

.add-ticker-row :deep(input) {
  flex: 1;
  max-width: 300px;
}

.tickers-table {
  margin-top: 0.5rem;
}

.ticker-symbol {
  font-weight: 600;
  color: var(--accent-green);
}

.date-text {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

.mono {
  font-family: var(--font-mono);
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
}

.loading-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-500, #666);
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.dialog-form label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--p-surface-300, #aaa);
}

.full-width {
  width: 100%;
}
</style>
