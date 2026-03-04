<script setup lang="ts">
import ToggleButton from 'primevue/togglebutton'
import type { ThemeInfo } from '@/types/scan'

/** Per-theme accent colors using PrimeVue CSS variables. */
const THEME_COLORS: Record<string, string> = {
  'AI & Machine Learning': 'var(--p-blue-400)',
  'Cannabis': 'var(--p-green-400)',
  'Electric Vehicles': 'var(--p-cyan-400)',
  'Clean Energy': 'var(--p-teal-400)',
  'Cybersecurity': 'var(--p-red-400)',
  'Popular Options': 'var(--p-orange-400)',
}

interface Props {
  themes: ThemeInfo[]
  selectedThemes?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  selectedThemes: () => [],
})

const emit = defineEmits<{
  'update:selectedThemes': [themes: string[]]
}>()

function toggleTheme(themeName: string): void {
  const current = [...props.selectedThemes]
  const idx = current.indexOf(themeName)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(themeName)
  emit('update:selectedThemes', current)
}

function isSelected(themeName: string): boolean {
  return props.selectedThemes.includes(themeName)
}

function themeColor(themeName: string): string {
  return THEME_COLORS[themeName] ?? 'var(--p-primary-400)'
}
</script>

<template>
  <div v-if="themes.length > 0" class="theme-chips" data-testid="theme-chips">
    <label class="theme-label">Investment Themes</label>
    <div class="theme-grid">
      <ToggleButton
        v-for="theme in themes"
        :key="theme.name"
        :modelValue="isSelected(theme.name)"
        :onLabel="`${theme.name} (${theme.ticker_count})`"
        :offLabel="`${theme.name} (${theme.ticker_count})`"
        class="theme-chip"
        :style="{ '--theme-color': themeColor(theme.name) }"
        :data-testid="`theme-chip-${theme.name}`"
        @update:modelValue="toggleTheme(theme.name)"
      />
    </div>
  </div>
</template>

<style scoped>
.theme-chips {
  margin-top: 0.75rem;
}

.theme-label {
  font-size: 0.85rem;
  color: var(--p-surface-400, #888);
  margin-bottom: 0.5rem;
  display: block;
}

.theme-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.theme-chip {
  font-size: 0.8rem;
}

.theme-chip:deep(.p-togglebutton-checked) {
  border-color: var(--theme-color, var(--p-primary-400));
  background: color-mix(in srgb, var(--theme-color, var(--p-primary-400)) 20%, transparent);
  color: var(--theme-color, var(--p-primary-400));
}
</style>
