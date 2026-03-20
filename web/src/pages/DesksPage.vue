<script setup lang="ts">
import DeskSelector from '@/components/DeskSelector.vue'
</script>

<template>
  <div class="desks-page">
    <h1>AI Desk Agents</h1>
    <p class="subtitle">Select a desk to ask a domain-specific question about any ticker.</p>
    <DeskSelector />
  </div>
</template>

<style scoped>
.desks-page {
  max-width: 1200px;
  margin: 0 auto;
}

.desks-page h1 {
  margin: 0 0 0.25rem 0;
}

.subtitle {
  margin: 0 0 1.5rem 0;
  font-size: 0.9rem;
  color: var(--p-surface-400, #888);
}
</style>
