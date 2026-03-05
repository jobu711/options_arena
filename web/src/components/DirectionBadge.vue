<script setup lang="ts">
interface Props {
  direction: 'bullish' | 'bearish' | 'neutral'
}

defineProps<Props>()
</script>

<template>
  <span class="direction-badge" :class="`dir--${direction}`" data-testid="direction-badge">
    {{ direction }}
  </span>
</template>

<style scoped>
.direction-badge {
  display: inline-block;
  text-transform: capitalize;
  font-size: 0.8rem;
  font-weight: 500;
  padding: 0.15rem 0.5rem;
  border-radius: 0.25rem;
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
  color: #000;
}
</style>
