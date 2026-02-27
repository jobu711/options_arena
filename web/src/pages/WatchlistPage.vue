<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import WatchlistManager from '@/components/WatchlistManager.vue'
import { useWatchlistStore } from '@/stores/watchlist'
import { ApiError } from '@/composables/useApi'
import type { Watchlist } from '@/types'

const toast = useToast()
const store = useWatchlistStore()

const selectedWatchlistId = ref<number | null>(null)
const createDialogVisible = ref(false)
const deleteDialogVisible = ref(false)
const watchlistToDelete = ref<Watchlist | null>(null)
const newName = ref('')
const newDescription = ref('')
const creating = ref(false)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function selectWatchlist(id: number): void {
  selectedWatchlistId.value = id
}

function openCreateDialog(): void {
  newName.value = ''
  newDescription.value = ''
  createDialogVisible.value = true
}

async function handleCreate(): Promise<void> {
  if (!newName.value.trim()) return

  creating.value = true
  try {
    const created = await store.createWatchlist(
      newName.value.trim(),
      newDescription.value.trim() || undefined,
    )
    createDialogVisible.value = false
    selectedWatchlistId.value = created.id
    toast.add({ severity: 'success', summary: 'Created', detail: `Watchlist "${created.name}" created`, life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to create watchlist'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  } finally {
    creating.value = false
  }
}

function confirmDelete(watchlist: Watchlist): void {
  watchlistToDelete.value = watchlist
  deleteDialogVisible.value = true
}

async function handleDelete(): Promise<void> {
  if (!watchlistToDelete.value) return

  try {
    const name = watchlistToDelete.value.name
    await store.deleteWatchlist(watchlistToDelete.value.id)
    if (selectedWatchlistId.value === watchlistToDelete.value.id) {
      selectedWatchlistId.value = null
    }
    deleteDialogVisible.value = false
    watchlistToDelete.value = null
    toast.add({ severity: 'success', summary: 'Deleted', detail: `Watchlist "${name}" deleted`, life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to delete watchlist'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  }
}

onMounted(() => void store.fetchWatchlists())
</script>

<template>
  <div class="page">
    <h1 data-testid="watchlist-title">Watchlists</h1>

    <!-- Toolbar -->
    <div class="toolbar">
      <Button
        label="Create Watchlist"
        icon="pi pi-plus"
        severity="success"
        data-testid="create-watchlist-btn"
        @click="openCreateDialog()"
      />
    </div>

    <div class="watchlist-layout">
      <!-- Watchlist List -->
      <section class="watchlist-list-section">
        <DataTable
          :value="store.watchlists"
          :loading="store.loading && !selectedWatchlistId"
          dataKey="id"
          :rows="20"
          responsiveLayout="scroll"
          selectionMode="single"
          class="watchlist-table"
          data-testid="watchlist-list-table"
          @row-click="(e: { data: Watchlist }) => selectWatchlist(e.data.id)"
        >
          <Column header="Name" field="name" :style="{ minWidth: '150px' }">
            <template #body="{ data }">
              <div class="watchlist-name-cell">
                <span
                  class="watchlist-name"
                  :class="{ active: selectedWatchlistId === data.id }"
                >
                  {{ data.name }}
                </span>
                <span v-if="data.description" class="watchlist-desc">
                  {{ data.description }}
                </span>
              </div>
            </template>
          </Column>
          <Column header="Updated" field="updated_at" :style="{ width: '180px' }">
            <template #body="{ data }">
              <span class="date-text">{{ formatDate(data.updated_at) }}</span>
            </template>
          </Column>
          <Column header="" :style="{ width: '60px', textAlign: 'center' }">
            <template #body="{ data }">
              <Button
                icon="pi pi-trash"
                severity="danger"
                text
                rounded
                size="small"
                :aria-label="`Delete ${data.name}`"
                :data-testid="`delete-watchlist-${data.id}`"
                @click.stop="confirmDelete(data as Watchlist)"
              />
            </template>
          </Column>
          <template #empty>
            <div class="empty-msg" data-testid="watchlist-list-empty">
              No watchlists yet. Create your first watchlist above.
            </div>
          </template>
        </DataTable>
      </section>

      <!-- Watchlist Detail -->
      <section v-if="selectedWatchlistId" class="watchlist-detail-section">
        <WatchlistManager :watchlist-id="selectedWatchlistId" />
      </section>
    </div>

    <!-- Create Dialog -->
    <Dialog
      v-model:visible="createDialogVisible"
      header="Create Watchlist"
      :style="{ width: '420px' }"
      modal
      data-testid="create-watchlist-dialog"
    >
      <div class="dialog-form">
        <label for="create-name">Name</label>
        <InputText
          id="create-name"
          v-model="newName"
          placeholder="e.g. Tech Growth"
          class="full-width"
          data-testid="create-watchlist-name"
          @keyup.enter="handleCreate()"
        />
        <label for="create-desc">Description (optional)</label>
        <Textarea
          id="create-desc"
          v-model="newDescription"
          rows="3"
          placeholder="Optional description..."
          class="full-width"
          data-testid="create-watchlist-description"
        />
      </div>
      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          @click="createDialogVisible = false"
        />
        <Button
          label="Create"
          icon="pi pi-check"
          :loading="creating"
          :disabled="!newName.trim()"
          data-testid="confirm-create-btn"
          @click="handleCreate()"
        />
      </template>
    </Dialog>

    <!-- Delete Confirmation Dialog -->
    <Dialog
      v-model:visible="deleteDialogVisible"
      header="Delete Watchlist"
      :style="{ width: '380px' }"
      modal
      data-testid="delete-watchlist-dialog"
    >
      <p>
        Are you sure you want to delete
        <strong>{{ watchlistToDelete?.name }}</strong>?
        This will remove all tickers in this watchlist.
      </p>
      <template #footer>
        <Button
          label="Cancel"
          severity="secondary"
          text
          @click="deleteDialogVisible = false"
        />
        <Button
          label="Delete"
          icon="pi pi-trash"
          severity="danger"
          data-testid="confirm-delete-btn"
          @click="handleDelete()"
        />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.toolbar {
  margin-bottom: 1.5rem;
}

.watchlist-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  align-items: start;
}

@media (max-width: 900px) {
  .watchlist-layout {
    grid-template-columns: 1fr;
  }
}

.watchlist-list-section {
  min-width: 0;
}

.watchlist-detail-section {
  min-width: 0;
  border-left: 1px solid var(--p-surface-700, #333);
  padding-left: 1.5rem;
}

@media (max-width: 900px) {
  .watchlist-detail-section {
    border-left: none;
    padding-left: 0;
    border-top: 1px solid var(--p-surface-700, #333);
    padding-top: 1.5rem;
  }
}

.watchlist-table :deep(tr) {
  cursor: pointer;
}

.watchlist-table :deep(tr:hover td) {
  background: var(--p-surface-700, #2a2a2a) !important;
}

.watchlist-name-cell {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.watchlist-name {
  font-weight: 600;
}

.watchlist-name.active {
  color: var(--accent-green);
}

.watchlist-desc {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 250px;
}

.date-text {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
}

.empty-msg {
  text-align: center;
  padding: 2rem;
  color: var(--p-surface-400, #888);
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
