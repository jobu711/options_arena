<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import HealthDot from '@/components/HealthDot.vue'
import SparklineChart from '@/components/SparklineChart.vue'
import DebateProgressModal from '@/components/DebateProgressModal.vue'
import { useHealthStore } from '@/stores/health'
import { useDebateStore } from '@/stores/debate'
import { useWebSocket } from '@/composables/useWebSocket'
import { api, ApiError } from '@/composables/useApi'
import type { ScanRun, DebateResultSummary, ConfigResponse, DebateEvent, TrendingTicker } from '@/types'

const router = useRouter()
const toast = useToast()
const healthStore = useHealthStore()
const debateStore = useDebateStore()

const latestScan = ref<ScanRun | null>(null)
const recentDebates = ref<DebateResultSummary[]>([])
const config = ref<ConfigResponse | null>(null)
const loading = ref(true)

// Trending data
const trendingUp = ref<TrendingTicker[]>([])
const trendingDown = ref<TrendingTicker[]>([])

// Quick debate state
const quickTicker = ref('')
const debateLoading = ref(false)
const showDebateProgress = ref(false)
const quickDebateTicker = ref('')
let closeWs: (() => void) | null = null

async function loadDashboard(): Promise<void> {
  loading.value = true
  try {
    const [scans, debates, cfg, bullish, bearish] = await Promise.all([
      api<ScanRun[]>('/api/scan', { params: { limit: 1 } }),
      api<DebateResultSummary[]>('/api/debate', { params: { limit: 5 } }),
      api<ConfigResponse>('/api/config'),
      api<TrendingTicker[]>('/api/ticker/trending', { params: { direction: 'bullish' } }).catch(() => [] as TrendingTicker[]),
      api<TrendingTicker[]>('/api/ticker/trending', { params: { direction: 'bearish' } }).catch(() => [] as TrendingTicker[]),
    ])
    latestScan.value = scans[0] ?? null
    recentDebates.value = debates
    config.value = cfg
    trendingUp.value = bullish.slice(0, 5)
    trendingDown.value = bearish.slice(0, 5)
  } finally {
    loading.value = false
  }
}

async function submitQuickDebate(): Promise<void> {
  const ticker = quickTicker.value.trim().toUpperCase()
  if (!ticker) return

  debateLoading.value = true
  quickDebateTicker.value = ticker
  debateStore.reset()

  try {
    const debateId = await debateStore.startDebate(ticker, null)
    showDebateProgress.value = true
    quickTicker.value = ''

    // Connect to WebSocket for progress
    const { close } = useWebSocket<DebateEvent>({
      url: `/ws/debate/${debateId}`,
      onMessage(event: DebateEvent) {
        switch (event.type) {
          case 'agent':
            debateStore.updateAgentProgress(event)
            break
          case 'error':
            debateStore.setDebateError(event.message)
            toast.add({
              severity: 'error',
              summary: 'Debate Error',
              detail: event.message,
              life: 5000,
            })
            break
          case 'complete':
            debateStore.setDebateComplete(event.debate_id)
            showDebateProgress.value = false
            void router.push(`/debate/${event.debate_id}`)
            break
        }
      },
      maxReconnectAttempts: 0,
    })
    closeWs = close
  } catch (err: unknown) {
    showDebateProgress.value = false
    if (err instanceof ApiError && err.status === 409) {
      toast.add({
        severity: 'warn',
        summary: 'Operation Busy',
        detail: 'Another operation is already in progress.',
        life: 5000,
      })
    } else {
      toast.add({
        severity: 'error',
        summary: 'Debate Failed',
        detail: err instanceof Error ? err.message : 'Failed to start debate',
        life: 5000,
      })
    }
  } finally {
    debateLoading.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function formatConfidence(val: number): string {
  return `${(val * 100).toFixed(0)}%`
}

onMounted(() => {
  void loadDashboard()
  void healthStore.fetchHealth()
  healthStore.startAutoRefresh(60_000)
})

onUnmounted(() => {
  healthStore.stopAutoRefresh()
  if (closeWs) closeWs()
})
</script>

<template>
  <div class="page">
    <h1>Dashboard</h1>

    <!-- Health Strip -->
    <div v-if="healthStore.services.length > 0" class="health-strip" data-testid="dashboard-health-strip">
      <span
        v-for="svc in healthStore.services"
        :key="svc.service_name"
        class="health-chip"
        :title="`${svc.service_name}: ${svc.available ? 'ok' : 'down'}`"
        :data-testid="`health-dot-${svc.service_name.toLowerCase().replace(/\\s/g, '-')}`"
      >
        <HealthDot :available="svc.available" :latency-ms="svc.latency_ms" />
        <span class="chip-label">{{ svc.service_name }}</span>
      </span>
    </div>

    <!-- Quick Actions -->
    <div class="quick-actions">
      <Button
        label="New Scan"
        icon="pi pi-play"
        severity="success"
        data-testid="dashboard-btn-new-scan"
        @click="router.push('/scan')"
      />
      <Button
        label="View Universe"
        icon="pi pi-globe"
        severity="secondary"
        data-testid="dashboard-btn-universe"
        @click="router.push('/universe')"
      />
      <Button
        label="Health Check"
        icon="pi pi-heart"
        severity="secondary"
        data-testid="dashboard-btn-health"
        @click="router.push('/health')"
      />
      <Button
        label="Watchlists"
        icon="pi pi-bookmark"
        severity="secondary"
        data-testid="dashboard-btn-watchlists"
        @click="router.push('/watchlist')"
      />

      <span class="quick-debate-separator" />

      <form class="quick-debate-form" @submit.prevent="submitQuickDebate">
        <InputText
          v-model="quickTicker"
          placeholder="Ticker"
          data-testid="quick-debate-input"
          class="quick-debate-input"
          :disabled="debateLoading"
          @input="quickTicker = quickTicker.toUpperCase()"
        />
        <Button
          label="Debate"
          icon="pi pi-comments"
          severity="info"
          data-testid="quick-debate-btn"
          :loading="debateLoading"
          :disabled="!quickTicker.trim() || debateLoading"
          @click="submitQuickDebate"
        />
      </form>
    </div>

    <!-- Debate Progress Modal -->
    <DebateProgressModal
      v-model:visible="showDebateProgress"
      :ticker="quickDebateTicker"
      :agents="debateStore.agentProgress"
      :error="debateStore.error"
    />

    <!-- Latest Scan Card -->
    <section class="section">
      <h2>Latest Scan</h2>
      <div v-if="latestScan" class="scan-card" data-testid="dashboard-latest-scan">
        <div class="scan-info">
          <span class="scan-preset">{{ latestScan.preset.toUpperCase() }}</span>
          <span class="scan-meta">
            {{ latestScan.tickers_scanned }} scanned /
            {{ latestScan.tickers_scored }} scored /
            {{ latestScan.recommendations }} recommendations
          </span>
          <span class="scan-date">{{ formatDate(latestScan.started_at) }}</span>
        </div>
        <Button
          label="View Results"
          icon="pi pi-arrow-right"
          size="small"
          severity="info"
          @click="router.push(`/scan/${latestScan.id}`)"
        />
      </div>
      <div v-else-if="!loading" class="empty-state" data-testid="empty-state">
        <i class="pi pi-inbox empty-icon" />
        <p class="empty-text">No scans yet. Run your first scan to get started.</p>
      </div>
    </section>

    <!-- Trending Up -->
    <section v-if="trendingUp.length > 0" class="section" data-testid="trending-up-section">
      <h2>Trending Up</h2>
      <DataTable
        :value="trendingUp"
        dataKey="ticker"
        :rows="5"
        class="trending-table"
      >
        <Column field="ticker" header="Ticker" :style="{ width: '80px' }">
          <template #body="{ data }">
            <span
              class="ticker-link mono"
              @click="router.push(`/ticker/${data.ticker}`)"
            >{{ data.ticker }}</span>
          </template>
        </Column>
        <Column header="Trend" :style="{ width: '100px' }">
          <template #body="{ data }">
            <SparklineChart
              :scores="[data.latest_score - data.score_change, data.latest_score]"
              :direction="data.direction"
            />
          </template>
        </Column>
        <Column field="latest_score" header="Score" :style="{ width: '70px' }">
          <template #body="{ data }">
            <span class="mono">{{ data.latest_score.toFixed(1) }}</span>
          </template>
        </Column>
        <Column field="consecutive_scans" header="Scans" :style="{ width: '60px' }">
          <template #body="{ data }">
            <span class="mono">{{ data.consecutive_scans }}</span>
          </template>
        </Column>
      </DataTable>
    </section>

    <!-- Trending Down -->
    <section v-if="trendingDown.length > 0" class="section" data-testid="trending-down-section">
      <h2>Trending Down</h2>
      <DataTable
        :value="trendingDown"
        dataKey="ticker"
        :rows="5"
        class="trending-table"
      >
        <Column field="ticker" header="Ticker" :style="{ width: '80px' }">
          <template #body="{ data }">
            <span
              class="ticker-link mono"
              @click="router.push(`/ticker/${data.ticker}`)"
            >{{ data.ticker }}</span>
          </template>
        </Column>
        <Column header="Trend" :style="{ width: '100px' }">
          <template #body="{ data }">
            <SparklineChart
              :scores="[data.latest_score - data.score_change, data.latest_score]"
              :direction="data.direction"
            />
          </template>
        </Column>
        <Column field="latest_score" header="Score" :style="{ width: '70px' }">
          <template #body="{ data }">
            <span class="mono">{{ data.latest_score.toFixed(1) }}</span>
          </template>
        </Column>
        <Column field="consecutive_scans" header="Scans" :style="{ width: '60px' }">
          <template #body="{ data }">
            <span class="mono">{{ data.consecutive_scans }}</span>
          </template>
        </Column>
      </DataTable>
    </section>

    <!-- Recent Debates -->
    <section class="section">
      <h2>Recent Debates</h2>
      <div v-if="recentDebates.length > 0" class="debate-list" data-testid="dashboard-recent-debates">
        <div
          v-for="debate in recentDebates"
          :key="debate.id"
          class="debate-row"
          @click="router.push(`/debate/${debate.id}`)"
        >
          <span class="debate-ticker">{{ debate.ticker }}</span>
          <span class="debate-direction" :class="`dir--${debate.direction}`">
            {{ debate.direction }}
          </span>
          <span class="debate-confidence mono">{{ formatConfidence(debate.confidence) }}</span>
          <span class="debate-date">{{ formatDate(debate.created_at) }}</span>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-state">
        <i class="pi pi-comments empty-icon" />
        <p class="empty-text">No debates yet.</p>
      </div>
    </section>

    <!-- Config Summary -->
    <section v-if="config" class="section">
      <h2>Configuration</h2>
      <div class="config-grid">
        <div class="config-item">
          <span class="config-label">Groq API Key</span>
          <span :class="config.groq_api_key_set ? 'status-ok' : 'status-down'">
            {{ config.groq_api_key_set ? 'Set' : 'Missing' }}
          </span>
        </div>
        <div class="config-item">
          <span class="config-label">Default Preset</span>
          <span class="config-value">{{ config.scan_preset_default }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">Rebuttal</span>
          <span class="config-value">{{ config.enable_rebuttal ? 'Enabled' : 'Disabled' }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">Volatility Agent</span>
          <span class="config-value">{{ config.enable_volatility_agent ? 'Enabled' : 'Disabled' }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.health-strip {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
  padding: 0.5rem 0;
}

.health-chip {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 1rem;
  padding: 0.25rem 0.75rem;
  font-size: 0.8rem;
  transition: background-color 0.15s, border-color 0.15s;
}

.health-chip:hover {
  background: var(--p-surface-700, #2a2a2a);
  border-color: var(--p-surface-600, #444);
}

.chip-label {
  text-transform: capitalize;
}

.quick-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.quick-debate-separator {
  width: 1px;
  height: 1.75rem;
  background: var(--p-surface-600, #444);
  flex-shrink: 0;
}

.quick-debate-form {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.quick-debate-input {
  width: 140px;
  min-width: 80px;
  max-width: 100%;
  text-transform: uppercase;
}

.section {
  margin-bottom: 2rem;
}

.section h2 {
  font-size: 1.1rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-200, #ccc);
}

.scan-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.scan-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.scan-preset {
  font-weight: 600;
  color: var(--accent-green);
}

.scan-meta {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
}

.scan-date {
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
}

.debate-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.debate-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: border-color 0.15s;
}

.debate-row:hover {
  border-color: var(--p-surface-500, #666);
}

.debate-ticker {
  font-weight: 600;
  min-width: 60px;
}

.debate-direction {
  text-transform: capitalize;
  font-size: 0.8rem;
  padding: 0.1rem 0.5rem;
  border-radius: 0.25rem;
  font-weight: 500;
}

.dir--bullish {
  background: var(--accent-green);
  color: #fff;
}

.dir--bearish {
  background: var(--accent-red);
  color: #fff;
}

.dir--neutral {
  background: var(--accent-yellow);
  color: #111;
}

.debate-confidence {
  font-size: 0.875rem;
  color: var(--p-surface-300, #aaa);
}

.debate-date {
  font-size: 0.75rem;
  color: var(--p-surface-500, #666);
  margin-left: auto;
}

.mono {
  font-family: var(--font-mono);
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0.75rem;
}

.config-item {
  display: flex;
  justify-content: space-between;
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.375rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
}

.config-label {
  color: var(--p-surface-400, #888);
}

.config-value {
  color: var(--p-surface-200, #ccc);
}

.status-ok {
  color: var(--accent-green);
}

.status-down {
  color: var(--accent-red);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 1.75rem;
  margin-bottom: 0.5rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0;
  font-size: 0.875rem;
}

.trending-table {
  font-size: 0.9rem;
}

.trending-table :deep(tr) {
  cursor: default;
}

.ticker-link {
  font-weight: 600;
  cursor: pointer;
  color: var(--p-surface-100, #eee);
  transition: color 0.15s;
}

.ticker-link:hover {
  color: var(--accent-blue, #3b82f6);
}
</style>
