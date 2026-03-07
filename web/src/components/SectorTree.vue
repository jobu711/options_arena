<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Tree from 'primevue/tree'
import Panel from 'primevue/panel'
import type { TreeNode } from 'primevue/treenode'
import type { TreeSelectionKeys } from 'primevue/tree'
import type { SectorHierarchy } from '@/types'

/** Accent color CSS values per GICS sector for tree node dots. */
const SECTOR_COLOR_MAP: Record<string, string> = {
  'Information Technology': 'var(--accent-blue, #3b82f6)',
  'Health Care': 'var(--accent-green, #22c55e)',
  'Financials': 'var(--p-surface-400, #888)',
  'Consumer Discretionary': 'var(--accent-yellow, #eab308)',
  'Communication Services': 'var(--p-surface-200, #ccc)',
  'Industrials': 'var(--p-surface-300, #aaa)',
  'Consumer Staples': '#4ade80',
  'Energy': 'var(--accent-red, #ef4444)',
  'Utilities': '#94a3b8',
  'Real Estate': '#f59e0b',
  'Materials': '#a78bfa',
}

interface Props {
  sectors: SectorHierarchy[]
  selectedSectors?: string[]
  selectedIndustryGroups?: string[]
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selectedSectors: () => [],
  selectedIndustryGroups: () => [],
  disabled: false,
})

const emit = defineEmits<{
  'update:selectedSectors': [sectors: string[]]
  'update:selectedIndustryGroups': [groups: string[]]
}>()

/** Prefix for sector node keys to distinguish from industry group keys. */
const SECTOR_PREFIX = 'sector:'
const IG_PREFIX = 'ig:'

/** Build TreeNode[] from SectorHierarchy[]. */
const treeNodes = computed<TreeNode[]>(() =>
  props.sectors.map((sector) => ({
    key: `${SECTOR_PREFIX}${sector.name}`,
    label: `${sector.name} (${sector.ticker_count})`,
    data: { name: sector.name, type: 'sector' },
    children: sector.industry_groups.map((ig) => ({
      key: `${IG_PREFIX}${ig.name}`,
      label: `${ig.name} (${ig.ticker_count})`,
      leaf: true,
      data: { name: ig.name, type: 'industry_group' },
    })),
  })),
)

/** Build selectionKeys from external selectedSectors and selectedIndustryGroups props. */
function buildSelectionKeys(): TreeSelectionKeys {
  const keys: TreeSelectionKeys = {}
  const selectedSectorSet = new Set(props.selectedSectors)
  const selectedIgSet = new Set(props.selectedIndustryGroups)

  for (const sector of props.sectors) {
    const sectorKey = `${SECTOR_PREFIX}${sector.name}`
    const childKeys = sector.industry_groups.map((ig) => `${IG_PREFIX}${ig.name}`)
    const allChildrenSelected =
      childKeys.length > 0 && childKeys.every((ck) => selectedIgSet.has(ck.slice(IG_PREFIX.length)))
    const someChildrenSelected = childKeys.some((ck) =>
      selectedIgSet.has(ck.slice(IG_PREFIX.length)),
    )

    if (selectedSectorSet.has(sector.name) || allChildrenSelected) {
      // Fully checked sector
      keys[sectorKey] = { checked: true, partialChecked: false }
      for (const ig of sector.industry_groups) {
        keys[`${IG_PREFIX}${ig.name}`] = { checked: true, partialChecked: false }
      }
    } else if (someChildrenSelected) {
      // Partially checked sector
      keys[sectorKey] = { checked: false, partialChecked: true }
      for (const ig of sector.industry_groups) {
        const igKey = `${IG_PREFIX}${ig.name}`
        if (selectedIgSet.has(ig.name)) {
          keys[igKey] = { checked: true, partialChecked: false }
        }
      }
    }
  }
  return keys
}

const selectionKeys = ref<TreeSelectionKeys>(buildSelectionKeys())

// Sync external prop changes to internal selectionKeys
let suppressEmit = false
watch(
  [() => props.selectedSectors, () => props.selectedIndustryGroups],
  () => {
    suppressEmit = true
    selectionKeys.value = buildSelectionKeys()
    suppressEmit = false
  },
  { deep: true },
)

/** Decompose selectionKeys into sector and industry group arrays for emission. */
function onSelectionChange(newKeys: TreeSelectionKeys): void {
  selectionKeys.value = newKeys
  if (suppressEmit) return

  const sectors: string[] = []
  const industryGroups: string[] = []

  for (const sector of props.sectors) {
    const sectorKey = `${SECTOR_PREFIX}${sector.name}`
    const sectorEntry = newKeys[sectorKey] as
      | { checked: boolean; partialChecked: boolean }
      | undefined

    if (sectorEntry?.checked && !sectorEntry.partialChecked) {
      // Fully checked sector — emit as a sector filter
      sectors.push(sector.name)
    } else if (sectorEntry?.partialChecked || sectorEntry?.checked) {
      // Partially checked — emit individual industry groups
      for (const ig of sector.industry_groups) {
        const igKey = `${IG_PREFIX}${ig.name}`
        const igEntry = newKeys[igKey] as
          | { checked: boolean; partialChecked: boolean }
          | undefined
        if (igEntry?.checked) {
          industryGroups.push(ig.name)
        }
      }
    }
  }

  emit('update:selectedSectors', sectors)
  emit('update:selectedIndustryGroups', industryGroups)
}

/** Count selected sectors + industry groups for the panel header badge. */
const selectedCount = computed(() => {
  let count = 0
  for (const key of Object.keys(selectionKeys.value)) {
    const entry = selectionKeys.value[key] as { checked: boolean; partialChecked: boolean } | undefined
    if (entry?.checked && !entry.partialChecked) count++
  }
  return count
})

const panelHeader = computed(() => {
  const base = 'Sectors (S&P 500 only)'
  return selectedCount.value > 0 ? `${base} \u2014 ${selectedCount.value} selected` : base
})

/** Get accent color CSS variable for a sector node. */
function sectorColor(sectorName: string): string {
  return SECTOR_COLOR_MAP[sectorName] ?? 'var(--p-surface-300, #aaa)'
}
</script>

<template>
  <div class="sector-tree-wrapper" data-testid="sector-tree">
    <Panel :header="panelHeader" :toggleable="true" :collapsed="true">
      <Tree
        :value="treeNodes"
        selectionMode="checkbox"
        :selectionKeys="selectionKeys"
        :disabled="disabled"
        filter
        filterPlaceholder="Search sectors..."
        class="sector-tree"
        @update:selectionKeys="onSelectionChange"
      >
        <template #default="{ node }">
          <span class="tree-node-label" :class="{ 'tree-node-sector': node.data?.type === 'sector' }">
            <span
              v-if="node.data?.type === 'sector'"
              class="sector-dot"
              :style="{ backgroundColor: sectorColor(node.data.name) }"
            />
            {{ node.label }}
          </span>
        </template>
      </Tree>
    </Panel>
  </div>
</template>

<style scoped>
.sector-tree-wrapper {
  min-width: 250px;
  max-width: 100%;
}

.sector-tree {
  border: 1px solid var(--p-surface-700, #333);
  border-radius: 0.5rem;
  max-height: 220px;
  overflow-y: auto;
}

.tree-node-label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}

.tree-node-sector {
  font-weight: 600;
}

.sector-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
