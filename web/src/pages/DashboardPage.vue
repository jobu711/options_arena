<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import ToggleSwitch from 'primevue/toggleswitch'
import HealthDot from '@/components/HealthDot.vue'
import { useHealthStore } from '@/stores/health'
import { api } from '@/composables/useApi'
import type { ScanRun, DebateResultSummary, ConfigResponse } from '@/types'

const router = useRouter()
const healthStore = useHealthStore()

const latestScan = ref<ScanRun | null>(null)
const recentDebates = ref<DebateResultSummary[]>([])
const config = ref<ConfigResponse | null>(null)
const loading = ref(true)
const lastUpdated = ref<Date | null>(null)
const autoRefreshEnabled = ref(localStorage.getItem('dashboard_auto_refresh') !== 'false')
const now = ref(new Date())
let dashboardInterval: ReturnType<typeof setInterval> | null = null
let nowInterval: ReturnType<typeof setInterval> | null = null

const lastUpdatedText = computed<string>(() => {
  if (!lastUpdated.value) return ''
  const diffMs = now.value.getTime() - lastUpdated.value.getTime()
  const seconds = Math.floor(diffMs / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ago`
})

async function loadDashboard(): Promise<void> {
  loading.value = true
  try {
    const [scans, debates, cfg] = await Promise.all([
      api<ScanRun[]>('/api/scan', { params: { limit: 1 } }),
      api<DebateResultSummary[]>('/api/debate', { params: { limit: 5 } }),
      api<ConfigResponse>('/api/config'),
    ])
    latestScan.value = scans[0] ?? null
    recentDebates.value = debates
    config.value = cfg
    lastUpdated.value = new Date()
  } finally {
    loading.value = false
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

function formatConfidence(val: number): string {
  return `${(val * 100).toFixed(0)}%`
}

function startDashboardRefresh(): void {
  stopDashboardRefresh()
  dashboardInterval = setInterval(() => void loadDashboard(), 60_000)
}

function stopDashboardRefresh(): void {
  if (dashboardInterval !== null) {
    clearInterval(dashboardInterval)
    dashboardInterval = null
  }
}

function toggleAutoRefresh(): void {
  localStorage.setItem('dashboard_auto_refresh', String(autoRefreshEnabled.value))
  if (autoRefreshEnabled.value) {
    startDashboardRefresh()
  } else {
    stopDashboardRefresh()
  }
}

onMounted(() => {
  void loadDashboard()
  void healthStore.fetchHealth()
  healthStore.startAutoRefresh(30_000)
  if (autoRefreshEnabled.value) {
    startDashboardRefresh()
  }
  nowInterval = setInterval(() => { now.value = new Date() }, 1_000)
})

onUnmounted(() => {
  healthStore.stopAutoRefresh()
  stopDashboardRefresh()
  if (nowInterval !== null) {
    clearInterval(nowInterval)
    nowInterval = null
  }
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Dashboard</h1>
      <div class="header-controls">
        <span v-if="lastUpdated" class="last-updated mono">{{ lastUpdatedText }}</span>
        <div class="refresh-toggle">
          <label class="toggle-label">Auto-refresh</label>
          <ToggleSwitch v-model="autoRefreshEnabled" @change="toggleAutoRefresh" />
        </div>
      </div>
    </div>

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
    </div>

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
      <p v-else-if="!loading" class="empty-msg" data-testid="empty-state">No scans yet. Run your first scan to get started.</p>
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
      <p v-else-if="!loading" class="empty-msg">No debates yet.</p>
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
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.page-header h1 {
  margin: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.last-updated {
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
}

.refresh-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.toggle-label {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
}

.health-strip {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
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
}

.chip-label {
  text-transform: capitalize;
}

.quick-actions {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 2rem;
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

.empty-msg {
  color: var(--p-surface-400, #888);
  font-size: 0.875rem;
}
</style>
