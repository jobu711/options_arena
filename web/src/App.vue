<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import Toast from 'primevue/toast'
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
    <nav class="app-nav">
      <div class="nav-brand">Options Arena</div>
      <div class="nav-links">
        <RouterLink to="/" class="nav-link" data-testid="nav-link-dashboard">Dashboard</RouterLink>
        <RouterLink to="/scan" class="nav-link" data-testid="nav-link-scan">Scan</RouterLink>
        <RouterLink to="/analytics" class="nav-link" data-testid="nav-link-analytics">Analytics</RouterLink>
      </div>
    </nav>
    <main class="app-main">
      <RouterView />
    </main>
    <Toast />
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-nav {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--p-surface-700, #333);
  background: var(--p-surface-900, #111);
}

.nav-brand {
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--accent-green);
}

.nav-links {
  display: flex;
  gap: 1rem;
}

.nav-link {
  color: var(--p-surface-300, #aaa);
  text-decoration: none;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  transition: color 0.15s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #fff;
}

.app-main {
  flex: 1;
  padding: 1.5rem;
}
</style>
