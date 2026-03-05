<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import Button from 'primevue/button'
import HealthDot from '@/components/HealthDot.vue'
import { useHealthStore } from '@/stores/health'

const healthStore = useHealthStore()

onMounted(() => {
  void healthStore.fetchHealth()
  healthStore.startAutoRefresh(60_000)
})

onUnmounted(() => {
  healthStore.stopAutoRefresh()
})

function formatLatency(ms: number | null): string {
  if (ms === null) return '--'
  return `${ms.toFixed(0)}ms`
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString()
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1>Service Health</h1>
      <Button
        label="Re-check"
        icon="pi pi-refresh"
        :loading="healthStore.loading"
        severity="secondary"
        size="small"
        data-testid="health-refresh-btn"
        @click="healthStore.fetchHealth()"
      />
    </div>

    <p v-if="healthStore.error" class="error-msg">{{ healthStore.error }}</p>

    <div v-if="healthStore.services.length === 0 && !healthStore.loading" class="empty-state">
      <i class="pi pi-heart empty-icon" />
      <p class="empty-text">No health data yet. Click Re-check to fetch service statuses.</p>
    </div>

    <div class="service-grid">
      <div
        v-for="svc in healthStore.services"
        :key="svc.service_name"
        class="service-card"
        :class="{ 'service-card--down': !svc.available }"
        :data-testid="`health-card-${svc.service_name.toLowerCase().replace(/\\s/g, '-')}`"
      >
        <div class="service-header">
          <HealthDot :available="svc.available" :latency-ms="svc.latency_ms" :data-testid="`health-dot-${svc.service_name.toLowerCase().replace(/\\s/g, '-')}`" />
          <span class="service-name">{{ svc.service_name }}</span>
        </div>
        <div class="service-details">
          <div class="detail-row">
            <span class="detail-label">Status</span>
            <span :class="svc.available ? 'status-ok' : 'status-down'">
              {{ svc.available ? 'Healthy' : 'Down' }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Latency</span>
            <span class="detail-value mono">{{ formatLatency(svc.latency_ms) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Checked</span>
            <span class="detail-value">{{ formatTime(svc.checked_at) }}</span>
          </div>
          <div v-if="svc.error" class="detail-row">
            <span class="detail-label">Error</span>
            <span class="detail-value error-text">{{ svc.error }}</span>
          </div>
        </div>
      </div>
    </div>

    <p v-if="healthStore.lastChecked" class="last-checked">
      Last checked: {{ healthStore.lastChecked.toLocaleTimeString() }}
    </p>
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

.service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.service-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
}

.service-card--down {
  border-color: var(--accent-red);
}

.service-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.service-name {
  font-weight: 600;
  text-transform: capitalize;
  font-size: 1.05rem;
}

.service-details {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
}

.detail-label {
  color: var(--p-surface-400, #888);
}

.detail-value {
  color: var(--p-surface-200, #ccc);
}

.mono {
  font-family: var(--font-mono);
}

.status-ok {
  color: var(--accent-green);
}

.status-down {
  color: var(--accent-red);
}

.error-text {
  color: var(--accent-red);
  font-size: 0.8rem;
}

.error-msg {
  color: var(--accent-red);
  margin-bottom: 1rem;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  border: 1px dashed var(--p-surface-600, #444);
  border-radius: 0.5rem;
  color: var(--p-surface-400, #888);
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.75rem;
  color: var(--p-surface-500, #666);
}

.empty-text {
  margin: 0;
  font-size: 0.9rem;
}

.last-checked {
  margin-top: 1rem;
  font-size: 0.8rem;
  color: var(--p-surface-500, #666);
}
</style>
