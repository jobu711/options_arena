---
title: "DashboardPage.vue retained deleted debate system toggles after cutover"
date: 2026-03-22
module: web.src.pages.DashboardPage
problem_type: integration_issue
severity: medium
symptoms:
  - "Frontend build fails with TypeScript error"
  - "'enableRebuttal' does not exist in type 'DebateOptions'"
  - "vue-tsc --noEmit fails during npm run build"
tags:
  - frontend
  - cutover
  - stale-reference
  - typescript
  - debate-system
root_cause: "Unified agent system cutover deleted debate agents and cleaned DebateOptions type but missed DashboardPage.vue references"
---

## Problem

`npm run build` (which runs `vue-tsc --noEmit && vite build`) failed with:

```
src/pages/DashboardPage.vue(80,7): error TS2353: Object literal may only specify
known properties, and 'enableRebuttal' does not exist in type 'DebateOptions'.
```

The `DashboardPage.vue` quick-debate form still passed `enableRebuttal` and
`enableVolatilityAgent` options from the old 3-agent debate system, but the
`DebateOptions` interface in `stores/debate.ts` had been updated to only contain
`scanId` during the unified agent system cutover (epic/unified-agent-system-cutover).

## Root Cause

The cutover epic (PR #691, -7,445 lines) deleted 13 debate files and updated the
recommendation pipeline, but missed 4 leftover references in `DashboardPage.vue`:

1. `import Checkbox from 'primevue/checkbox'` (line 6)
2. `const enableRebuttal = ref(false)` / `const enableVolatilityAgent = ref(false)` (lines 40-41)
3. `enableRebuttal` / `enableVolatilityAgent` in `startDebate()` options object (lines 80-81)
4. Checkbox template elements for the two toggles (lines 238-244)
5. `.debate-toggles` / `.debate-toggle` CSS classes (lines 513-526)

The TypeScript compiler caught this because `DebateOptions` was correctly narrowed,
but the references in the Vue SFC weren't caught by the Python-side review.

## Solution

Removed all 5 leftover references:
- Deleted `Checkbox` import
- Deleted `enableRebuttal` and `enableVolatilityAgent` refs
- Simplified `startDebate(ticker, null)` call (no options object)
- Deleted checkbox template elements
- Deleted associated CSS classes

No E2E tests referenced these elements (verified via grep).

## Prevention Rule

After large-scale cutover epics that delete backend features:
- Run `npm run build` (not just `vite build`) to catch TypeScript errors in Vue SFCs
- Grep the `web/` directory for any references to deleted model fields or option names
- Check both `<script>`, `<template>`, and `<style>` sections of Vue components
- The Python test suite won't catch frontend regressions — always verify the frontend build

## Related

- PR #691 — unified-agent-system-cutover epic
- `web/src/pages/DashboardPage.vue` — quick-debate form
- `web/src/stores/debate.ts` — `DebateOptions` interface
