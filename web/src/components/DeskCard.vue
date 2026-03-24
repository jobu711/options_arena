<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  title: string
  collapsed?: boolean
  fullWidth?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: false,
  fullWidth: false,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
}>()

const chevronClass = computed(() =>
  props.collapsed ? 'pi pi-chevron-down chevron chevron--collapsed' : 'pi pi-chevron-down chevron',
)

function toggle(): void {
  emit('update:collapsed', !props.collapsed)
}
</script>

<template>
  <div
    class="desk-card"
    :class="{ 'desk-card--full-width': fullWidth }"
    data-testid="desk-card"
  >
    <div class="desk-card__header" @click="toggle">
      <span class="desk-card__title">{{ title }}</span>
      <div class="desk-card__header-right">
        <slot name="status" />
        <i :class="chevronClass" />
      </div>
    </div>
    <div v-show="!collapsed" class="desk-card__body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.desk-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.75rem;
  overflow: hidden;
}

.desk-card--full-width {
  grid-column: 1 / -1;
}

.desk-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  user-select: none;
}

.desk-card__header:hover {
  background: var(--p-surface-700, #333);
}

.desk-card__title {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--p-surface-200, #ccc);
}

.desk-card__header-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chevron {
  font-size: 0.75rem;
  color: var(--p-surface-400, #888);
  transition: transform 0.2s ease;
}

.chevron--collapsed {
  transform: rotate(-90deg);
}

.desk-card__body {
  padding: 1rem;
  border-top: 1px solid var(--p-surface-700, #333);
}
</style>
