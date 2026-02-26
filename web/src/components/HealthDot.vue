<script setup lang="ts">
interface Props {
  available: boolean
  latencyMs: number | null
}

const props = defineProps<Props>()

function dotClass(): string {
  if (!props.available) return 'dot--down'
  if (props.latencyMs !== null && props.latencyMs > 500) return 'dot--degraded'
  return 'dot--ok'
}
</script>

<template>
  <span class="health-dot" :class="dotClass()" :title="available ? 'Healthy' : 'Down'" />
</template>

<style scoped>
.health-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot--ok {
  background: var(--accent-green);
  box-shadow: 0 0 6px var(--accent-green);
}

.dot--degraded {
  background: var(--accent-yellow);
  box-shadow: 0 0 6px var(--accent-yellow);
}

.dot--down {
  background: var(--accent-red);
  box-shadow: 0 0 6px var(--accent-red);
}
</style>
