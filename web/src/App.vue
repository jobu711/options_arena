<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import Toast from 'primevue/toast'
import HealthDot from '@/components/HealthDot.vue'
import { useHealthStore } from '@/stores/health'
import { useOperationStore } from '@/stores/operation'

const healthStore = useHealthStore()
const operationStore = useOperationStore()

onMounted(async () => {
  // Fetch initial health status to populate the store on app load (AUDIT-027)
  try {
    await healthStore.fetchHealth()
  } catch {
    // Health check failed — store keeps default unhealthy state
  }

  // Sync operation state from backend status endpoint
  await operationStore.syncFromServer()
})
</script>

<template>
  <div class="app-layout">
    <header class="top-bar">
      <RouterLink to="/" class="brand">OPTIONS ARENA</RouterLink>
      <nav class="nav-links">
        <RouterLink to="/" class="nav-link" data-testid="nav-link-trading-desk">
          Trading Desk
        </RouterLink>
        <RouterLink to="/analytics" class="nav-link" data-testid="nav-link-analytics">
          Analytics
        </RouterLink>
        <RouterLink to="/history" class="nav-link" data-testid="nav-link-history">
          History
        </RouterLink>
        <RouterLink to="/settings" class="nav-link" data-testid="nav-link-settings">
          Settings
        </RouterLink>
      </nav>
      <div class="status-area">
        <HealthDot
          :available="healthStore.allHealthy"
          :latency-ms="null"
          data-testid="app-health-dot"
        />
      </div>
    </header>
    <main class="content">
      <RouterView />
    </main>
    <Toast />
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--p-surface-950, #0a0a0a);
}

.top-bar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--p-surface-800, #262626);
  background: var(--p-surface-950, #0a0a0a);
}

.brand {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.15em;
  color: var(--accent-green);
  text-decoration: none;
  flex-shrink: 0;
}

.nav-links {
  display: flex;
  gap: 0.25rem;
}

.nav-link {
  color: var(--p-surface-400, #999);
  text-decoration: none;
  font-size: 0.8rem;
  padding: 0.25rem 0.75rem;
  border-radius: 0.25rem;
  transition: color 0.15s, background 0.15s;
}

.nav-link:hover {
  color: var(--p-surface-100, #eee);
  background: var(--p-surface-800, #262626);
}

.nav-link.router-link-exact-active {
  color: #fff;
  background: var(--p-surface-800, #262626);
}

.status-area {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.content {
  flex: 1;
}
</style>
