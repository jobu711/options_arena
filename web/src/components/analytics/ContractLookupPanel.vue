<script setup lang="ts">
import { ref } from 'vue'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { api, ApiError } from '@/composables/useApi'
import type { RecommendedContract } from '@/types'

const toast = useToast()
const ticker = ref('')
const limit = ref(25)
const contracts = ref<RecommendedContract[]>([])
const loading = ref(false)
const searched = ref(false)

const limitOptions = [
  { label: '10', value: 10 },
  { label: '25', value: 25 },
  { label: '50', value: 50 },
  { label: '100', value: 100 },
]

function formatPrice(value: string | null): string {
  if (value === null) return '--'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function formatGreek(value: number | null, decimals: number = 4): string {
  if (value === null || !isFinite(value)) return '--'
  return value.toFixed(decimals)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function directionSeverity(dir: string): 'success' | 'danger' | 'warn' {
  if (dir === 'BULLISH') return 'success'
  if (dir === 'BEARISH') return 'danger'
  return 'warn'
}

async function fetchContracts(): Promise<void> {
  const t = ticker.value.trim().toUpperCase()
  if (!t) return

  loading.value = true
  searched.value = true
  try {
    contracts.value = await api<RecommendedContract[]>(
      `/api/analytics/ticker/${encodeURIComponent(t)}/contracts`,
      { params: { limit: limit.value } },
    )
  } catch (err: unknown) {
    contracts.value = []
    const message = err instanceof ApiError ? err.message : 'Failed to fetch contracts'
    toast.add({ severity: 'error', summary: 'Lookup Failed', detail: message, life: 5000 })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="contract-lookup" data-testid="contract-lookup-panel">
    <!-- Search controls -->
    <div class="contract-lookup__controls">
      <InputText
        v-model="ticker"
        placeholder="Ticker (e.g. AAPL)"
        class="contract-lookup__input"
        data-testid="contract-ticker-input"
        @keyup.enter="fetchContracts"
      />
      <Select
        v-model="limit"
        :options="limitOptions"
        optionLabel="label"
        optionValue="value"
        class="contract-lookup__limit"
        data-testid="contract-limit-select"
      />
      <Button
        label="Search"
        icon="pi pi-search"
        size="small"
        :loading="loading"
        :disabled="!ticker.trim()"
        data-testid="contract-search-btn"
        @click="fetchContracts"
      />
    </div>

    <!-- Empty state -->
    <div
      v-if="searched && !loading && contracts.length === 0"
      class="contract-lookup__empty"
      data-testid="contract-empty"
    >
      <i class="pi pi-inbox" />
      <span>No recommended contracts found for {{ ticker.toUpperCase() }}.</span>
    </div>

    <!-- Results table -->
    <DataTable
      v-if="contracts.length > 0"
      :value="contracts"
      :rows="50"
      dataKey="id"
      size="small"
      :scrollable="true"
      scrollHeight="400px"
      data-testid="contract-table"
      class="contract-lookup__table"
    >
      <Column field="created_at" header="Date" :sortable="true" style="min-width: 110px">
        <template #body="{ data }">
          <span class="mono">{{ formatTimestamp((data as RecommendedContract).created_at) }}</span>
        </template>
      </Column>
      <Column field="option_type" header="Type" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <Tag
            :value="(data as RecommendedContract).option_type.toUpperCase()"
            :severity="(data as RecommendedContract).option_type === 'call' ? 'success' : 'danger'"
          />
        </template>
      </Column>
      <Column field="direction" header="Dir" :sortable="true" style="min-width: 80px">
        <template #body="{ data }">
          <Tag
            :value="(data as RecommendedContract).direction"
            :severity="directionSeverity((data as RecommendedContract).direction)"
          />
        </template>
      </Column>
      <Column field="strike" header="Strike" :sortable="true" style="min-width: 90px">
        <template #body="{ data }">
          <span class="mono">{{ formatPrice((data as RecommendedContract).strike) }}</span>
        </template>
      </Column>
      <Column field="expiration" header="Exp" :sortable="true" style="min-width: 100px">
        <template #body="{ data }">
          <span class="mono">{{ formatDate((data as RecommendedContract).expiration) }}</span>
        </template>
      </Column>
      <Column field="entry_mid" header="Entry Mid" :sortable="true" style="min-width: 90px">
        <template #body="{ data }">
          <span class="mono">{{ formatPrice((data as RecommendedContract).entry_mid) }}</span>
        </template>
      </Column>
      <Column field="entry_stock_price" header="Stock" :sortable="true" style="min-width: 90px">
        <template #body="{ data }">
          <span class="mono">{{ formatPrice((data as RecommendedContract).entry_stock_price) }}</span>
        </template>
      </Column>
      <Column field="market_iv" header="IV" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <span class="mono">{{ ((data as RecommendedContract).market_iv * 100).toFixed(1) }}%</span>
        </template>
      </Column>
      <Column field="delta" header="Delta" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <span class="mono">{{ formatGreek((data as RecommendedContract).delta) }}</span>
        </template>
      </Column>
      <Column field="composite_score" header="Score" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <span class="mono">{{ (data as RecommendedContract).composite_score.toFixed(1) }}</span>
        </template>
      </Column>
      <Column field="volume" header="Vol" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <span class="mono">{{ (data as RecommendedContract).volume.toLocaleString() }}</span>
        </template>
      </Column>
      <Column field="open_interest" header="OI" :sortable="true" style="min-width: 70px">
        <template #body="{ data }">
          <span class="mono">{{ (data as RecommendedContract).open_interest.toLocaleString() }}</span>
        </template>
      </Column>
    </DataTable>

    <!-- Result count -->
    <div v-if="contracts.length > 0" class="contract-lookup__count">
      {{ contracts.length }} contract{{ contracts.length !== 1 ? 's' : '' }}
    </div>
  </div>
</template>

<style scoped>
.contract-lookup {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.contract-lookup__controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.contract-lookup__input {
  width: 140px;
  text-transform: uppercase;
}

.contract-lookup__limit {
  width: 80px;
}

.contract-lookup__empty {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem 0;
  color: var(--p-surface-400, #888);
  font-size: 0.9rem;
}

.contract-lookup__count {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  font-family: var(--font-mono);
}

.contract-lookup__table {
  font-size: 0.85rem;
}

.mono {
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .contract-lookup__controls {
    flex-wrap: wrap;
  }

  .contract-lookup__input {
    width: 100%;
  }
}
</style>
