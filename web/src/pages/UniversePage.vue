<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Button from 'primevue/button'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import type { UniverseStats } from '@/types'

const toast = useToast()
const stats = ref<UniverseStats | null>(null)
const loading = ref(false)
const refreshing = ref(false)

async function fetchStats(): Promise<void> {
  loading.value = true
  try {
    stats.value = await api<UniverseStats>('/api/universe')
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to load universe stats'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  } finally {
    loading.value = false
  }
}

async function refreshUniverse(): Promise<void> {
  refreshing.value = true
  try {
    stats.value = await api<UniverseStats>('/api/universe/refresh', { method: 'POST' })
    toast.add({ severity: 'success', summary: 'Refreshed', detail: 'Universe data updated', life: 3000 })
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to refresh universe'
    toast.add({ severity: 'error', summary: 'Error', detail: msg, life: 5000 })
  } finally {
    refreshing.value = false
  }
}

onMounted(() => void fetchStats())
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Ticker Universe</h1>
      <Button
        label="Refresh"
        icon="pi pi-refresh"
        :loading="refreshing"
        severity="secondary"
        size="small"
        @click="refreshUniverse()"
      />
    </div>

    <div v-if="stats" class="stats-bar">
      <div class="stat-card">
        <span class="stat-value mono">{{ stats.optionable_count.toLocaleString() }}</span>
        <span class="stat-label">Optionable Tickers</span>
      </div>
      <div class="stat-card">
        <span class="stat-value mono">{{ stats.sp500_count.toLocaleString() }}</span>
        <span class="stat-label">S&P 500 Constituents</span>
      </div>
    </div>

    <p v-if="loading && !stats" class="loading-msg">Loading universe stats...</p>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  margin: 0;
}

.stats-bar {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.stat-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 200px;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-green);
}

.stat-label {
  font-size: 0.875rem;
  color: var(--p-surface-400, #888);
}

.mono {
  font-family: var(--font-mono);
}

.loading-msg {
  color: var(--p-surface-400, #888);
}
</style>
