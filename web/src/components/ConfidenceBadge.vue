<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  value: number // 0.0–1.0
}

const props = defineProps<Props>()

const pct = computed(() => `${(props.value * 100).toFixed(0)}%`)

const level = computed(() => {
  if (props.value >= 0.7) return 'high'
  if (props.value >= 0.4) return 'medium'
  return 'low'
})
</script>

<template>
  <span class="confidence-badge" :class="`confidence--${level}`">
    {{ pct }}
  </span>
</template>

<style scoped>
.confidence-badge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
}

.confidence--high {
  background: rgba(34, 197, 94, 0.15);
  color: var(--accent-green);
}

.confidence--medium {
  background: rgba(234, 179, 8, 0.15);
  color: var(--accent-yellow);
}

.confidence--low {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-red);
}
</style>
