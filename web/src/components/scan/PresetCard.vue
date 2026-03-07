<script setup lang="ts">
import Badge from 'primevue/badge'

interface Props {
  preset: string
  label: string
  description: string
  count: number | null
  icon: string
  selected: boolean
  disabled: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  select: [preset: string]
}>()

function handleClick(): void {
  if (!props.disabled) {
    emit('select', props.preset)
  }
}
</script>

<template>
  <div
    class="preset-card"
    :class="{ selected: props.selected, disabled: props.disabled }"
    :data-testid="`preset-card-${props.preset}`"
    role="button"
    :tabindex="props.disabled ? -1 : 0"
    :aria-disabled="props.disabled"
    @click="handleClick"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <div class="preset-header">
      <span class="preset-icon pi" :class="props.icon" />
      <span class="preset-label">{{ props.label }}</span>
      <Badge v-if="props.count != null" :value="String(props.count)" severity="secondary" />
    </div>
    <p class="preset-description">{{ props.description }}</p>
  </div>
</template>

<style scoped>
.preset-card {
  background: var(--p-surface-800, #1a1a1a);
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  padding: 1rem;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.preset-card.selected {
  border-color: var(--accent-blue, #3b82f6);
  background: rgba(59, 130, 246, 0.08);
}

.preset-card:hover:not(.disabled) {
  border-color: var(--p-surface-500, #666);
}

.preset-card.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.preset-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.preset-icon {
  color: var(--accent-blue, #3b82f6);
  font-size: 1.1rem;
}

.preset-label {
  font-weight: 600;
  font-size: 0.95rem;
  flex: 1;
}

.preset-description {
  font-size: 0.8rem;
  color: var(--p-surface-400, #888);
  margin: 0;
  line-height: 1.4;
}
</style>
