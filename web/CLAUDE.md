# CLAUDE.md -- Web UI (`web/`)

## Purpose

The **Vue 3 SPA frontend** for Options Arena. This is a separate build target from the Python
package — it has its own `package.json`, `node_modules/`, and Vite toolchain. The frontend
consumes the FastAPI backend (`src/options_arena/api/`) via REST + WebSocket. It never imports
Python code directly.

The `web/` directory is a **presentation layer only**. All business logic, scoring, pricing,
and data persistence live in the Python backend. The frontend renders data, manages UI state,
and streams progress events — nothing more.

## Files

```
web/
    src/
        App.vue                  # Root component: layout shell, PrimeVue Toast host, nav
        main.ts                  # App bootstrap: createApp, router, pinia, PrimeVue plugin
        router/
            index.ts             # 6 routes: /, /scan, /scan/:id, /debate/:id, /watchlist, /ticker/:ticker
        stores/
            scan.ts              # Pinia store: scan list, current scan, progress state
            debate.ts            # Pinia store: debate list, current debate, agent progress
            health.ts            # Pinia store: service health statuses
            operation.ts         # Pinia store: global operation lock state (scan/batch in progress)
        pages/
            DashboardPage.vue    # Latest scan summary, health strip, quick actions
            ScanPage.vue         # Scan launcher + past scans list
            ScanResultsPage.vue  # Sortable/filterable ticker table for a single scan
            DebateResultPage.vue # Full agent arguments, thesis, export
        components/
            ProgressTracker.vue  # Multi-phase progress bar (scan phases, debate agents)
            AgentCard.vue        # Single agent's response (name, confidence, key points, risks)
            ConfidenceBadge.vue  # Numeric confidence as colored badge
            DirectionBadge.vue   # Bullish/bearish/neutral pill badge
            HealthDot.vue        # Colored status dot (ok/degraded/down)
            TickerDrawer.vue     # PrimeVue Drawer wrapper: indicators, contracts, debate history
            DebateProgressModal.vue  # PrimeVue Dialog: debate/batch progress overlay
        composables/
            useWebSocket.ts      # WebSocket connect/reconnect/parse with typed events
            useApi.ts            # Typed fetch wrapper (base URL, error handling, abort)
            useOperation.ts      # Global operation state (is scan/batch running?)
        api/
            client.ts            # Generated typed client from OpenAPI (via openapi-typescript)
        types/
            index.ts             # Re-exports all TypeScript interfaces
            scan.ts              # ScanRun, TickerScore, ScanProgress, PaginatedResponse
            debate.ts            # DebateResult, AgentResponse, TradeThesis, DebateProgress
            health.ts            # HealthStatus
            ws.ts                # WebSocket event discriminated unions
    public/
        favicon.ico
    index.html                   # Vite entry HTML
    package.json
    vite.config.ts               # Dev proxy to backend, build output to dist/
    tsconfig.json
    tsconfig.node.json
    .eslintrc.cjs                # ESLint config (Vue + TypeScript rules)
    .prettierrc                  # Prettier config (consistent with project style)
    env.d.ts                     # Vite env type declarations
```

---

## Architecture Rules

| Rule | Detail |
|------|--------|
| **Presentation only** | Zero business logic. No scoring, pricing, indicator math, or data transformations beyond display formatting. If you need to compute something, it belongs in the Python backend. |
| **Typed everything** | Every component prop, emit, store field, API response, and WebSocket event has a TypeScript type. No `any`. No untyped objects. |
| **Composition API only** | All components use `<script setup lang="ts">`. Never Options API. Never `defineComponent()` with `setup()` return. |
| **Pinia for shared state** | Cross-component state lives in Pinia stores. Component-local state uses `ref()`/`reactive()`. Never prop-drill more than 2 levels — use a store. |
| **Composables for reuse** | Shared logic (WebSocket, API calls, operation tracking) extracted into `composables/use*.ts`. Composables return typed refs and functions. |
| **PrimeVue for primitives** | Use PrimeVue components (DataTable, Drawer, Dialog, Toast, Button, Tag, Badge, ProgressBar, Skeleton) for standard UI. Only build custom components for domain-specific rendering (AgentCard, ConfidenceBadge, DirectionBadge). |
| **PrimeVue Aura dark theme** | Use `@primevue/themes/aura` dark preset. Override CSS variables for accent colors (green/red/blue/purple) in `variables.css`. Never override PrimeVue internals. |
| **Toast for notifications** | Use PrimeVue `ToastService` for success/error/warning messages. Auto-dismiss after 5s. Inject via `useToast()` composable. |
| **URL state for filters** | Scan results table sort, filter, and page params synced to URL query string via `vue-router`. Browser back/forward preserves state. Use `useRoute()` to read, `router.replace()` to update. |
| **Pages are thin** | Page components compose smaller components. A page file should be < 150 lines. If larger, extract a component. |
| **One component per file** | No multi-component `.vue` files. File name matches component name in PascalCase. |
| **No direct `fetch()`** | All API calls go through `useApi` composable or the generated client. Never raw `fetch()` or `XMLHttpRequest`. |

### Import Rules

| Can Import | Cannot Import |
|-----------|---------------|
| Vue 3 (`vue`, `vue-router`, `pinia`), PrimeVue components | Any Python module (this is a separate build target) |
| `composables/*` (from pages, components) | Backend internals (database, services, scan pipeline) |
| `stores/*` (from pages, components, composables) | Node server-side packages (`fs`, `path`, `child_process`) |
| `types/*` (from everywhere) | |
| `api/client.ts` (from stores, composables) | |
| Shared components (from pages) | Pages (from components — no circular deps) |

---

## Route Map (6 routes)

```typescript
// router/index.ts
const routes: RouteRecordRaw[] = [
  { path: '/',            name: 'dashboard',      component: () => import('../pages/DashboardPage.vue') },
  { path: '/scan',        name: 'scan',           component: () => import('../pages/ScanPage.vue') },
  { path: '/scan/:id',    name: 'scan-results',   component: () => import('../pages/ScanResultsPage.vue') },
  { path: '/debate/:id',  name: 'debate-result',  component: () => import('../pages/DebateResultPage.vue') },
]
```

All routes use lazy loading (`() => import(...)`). No eager imports for pages.

---

## Serialization Contract (Python → JSON → TypeScript)

The backend serializes Pydantic models to JSON. The frontend must handle these type mappings:

| Python Type | JSON Wire Format | TypeScript Type | Display Pattern |
|-------------|-----------------|-----------------|-----------------|
| `Decimal` (prices) | `"123.45"` (string) | `string` | Format with `Intl.NumberFormat`. Never parse to `number` — precision loss. |
| `datetime` (UTC) | `"2026-02-26T14:30:45+00:00"` | `string` | Parse with `new Date()`, format with `Intl.DateTimeFormat`. |
| `StrEnum` | `"bullish"` | `string` literal union | `type Direction = "bullish" \| "bearish" \| "neutral"` |
| `float` (scores, Greeks) | `0.4523` | `number` | Format to fixed decimals: scores 1dp, Greeks 4dp, percentages 1dp. |
| `int` (volume, OI) | `1500` | `number` | Format with `Intl.NumberFormat` (thousands separator). |
| `X \| None` | `null` | `T \| null` | Null-check before display. Show `"--"` for null values. |

**Critical: Prices are strings.** All `Decimal` fields (`strike`, `bid`, `ask`, `last`,
`current_price`) arrive as JSON strings. The frontend formats them for display but never
converts to JavaScript `number` — floating-point precision loss is unacceptable for prices.

```typescript
// WRONG — precision loss
const strike = parseFloat(contract.strike) // 123.45000000000001

// RIGHT — display formatting only
function formatPrice(price: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Number(price))
}
// Use formatPrice() ONLY for rendering. Never store the result or do math on it.
```

---

## TypeScript Type Patterns

### Discriminated Unions for WebSocket Events

```typescript
// types/ws.ts

// Server → Client (scan)
type ScanProgressEvent = {
  type: 'progress'
  phase: 'universe' | 'scoring' | 'options' | 'persist'
  current: number
  total: number
}
type ScanErrorEvent = { type: 'error'; ticker: string; message: string }
type ScanCompleteEvent = { type: 'complete'; scan_id: number; cancelled: boolean }
type ScanEvent = ScanProgressEvent | ScanErrorEvent | ScanCompleteEvent

// Server → Client (debate)
type DebateAgentEvent = {
  type: 'agent'
  name: 'bull' | 'bear' | 'rebuttal' | 'volatility' | 'risk'
  status: 'started' | 'completed' | 'failed'
  confidence: number | null
}
type DebateCompleteEvent = { type: 'complete'; debate_id: number }
type DebateEvent = DebateAgentEvent | DebateCompleteEvent

// Client → Server (both)
type CancelMessage = { type: 'cancel' }
```

Use `event.type` as the discriminant in `switch` statements — TypeScript narrows the type
automatically.

### API Response Types

```typescript
// types/scan.ts
interface ScanRun {
  id: number
  started_at: string        // ISO 8601
  completed_at: string | null
  preset: 'full' | 'sp500' | 'etfs'
  tickers_scanned: number
  tickers_scored: number
  recommendations: number
}

interface TickerScore {
  ticker: string
  composite_score: number
  direction: 'bullish' | 'bearish' | 'neutral'
  momentum_score: number
  value_score: number
  volatility_score: number
  technical_score: number
  signals: IndicatorSignals    // 18 named fields, all number | null
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}
```

### Props Typing Pattern

```typescript
// In <script setup lang="ts">
interface Props {
  score: TickerScore
  contracts: OptionContract[]
  showDebateButton?: boolean   // optional with default
}
const props = withDefaults(defineProps<Props>(), {
  showDebateButton: true,
})
```

Never use runtime prop validation (`type: Object as PropType<X>`) — use compile-time
`defineProps<T>()` only.

---

## Component Patterns

### DataTable (PrimeVue — Used Directly)

Use PrimeVue `DataTable` + `Column` directly in pages. No custom wrapper component.

```vue
<template>
  <DataTable
    :value="scores"
    :paginator="true"
    :rows="50"
    :rowsPerPageOptions="[25, 50, 100]"
    sortMode="single"
    :sortField="route.query.sort as string ?? 'composite_score'"
    :sortOrder="route.query.order === 'asc' ? 1 : -1"
    @sort="onSort"
    @page="onPage"
    selectionMode="multiple"
    v-model:selection="selectedTickers"
    :loading="loading"
    :virtualScrollerOptions="scores.length > 1000 ? { itemSize: 40 } : undefined"
    dataKey="ticker"
  >
    <Column field="ticker" header="Ticker" :sortable="true" />
    <Column field="composite_score" header="Score" :sortable="true">
      <template #body="{ data }">{{ data.composite_score.toFixed(1) }}</template>
    </Column>
    <Column field="direction" header="Direction" :sortable="true">
      <template #body="{ data }"><DirectionBadge :direction="data.direction" /></template>
    </Column>
    <!-- ... more columns -->
  </DataTable>
</template>
```

Sort, filter, and page events update URL query params via `router.replace()`:

```typescript
function onSort(event: DataTableSortEvent) {
  router.replace({ query: { ...route.query, sort: event.sortField, order: event.sortOrder === 1 ? 'asc' : 'desc' } })
}
```

Sort and filter happen **client-side** for scan results (loaded in full from the API).
Virtual scroll enabled automatically for > 1,000 rows via PrimeVue `virtualScrollerOptions`.

### AgentCard Layout

```
┌─────────────────────────────────────┐
│  [Bull Icon]  Bull Agent            │
│  Confidence: ████████░░ 72%         │
│                                     │
│  Key Points                         │
│  • Strong earnings momentum         │
│  • Technical breakout above 200 SMA │
│                                     │
│  Risks Cited                        │
│  • Extended P/E ratio               │
│  • Sector rotation risk             │
└─────────────────────────────────────┘
```

Color scheme per agent:
- Bull: green accent (`#22c55e`)
- Bear: red accent (`#ef4444`)
- Risk: blue accent (`#3b82f6`)
- Volatility: purple accent (`#a855f7`)
- Rebuttal: green accent, lighter shade (`#86efac`)

---

## Composable Patterns

### useWebSocket

```typescript
// composables/useWebSocket.ts
import { ref, onUnmounted } from 'vue'

interface UseWebSocketOptions<T> {
  url: string
  onMessage: (event: T) => void
  onError?: (error: Event) => void
  reconnectInterval?: number       // ms, default 2000
  maxReconnectAttempts?: number    // default 5
}

export function useWebSocket<T>(options: UseWebSocketOptions<T>) {
  const connected = ref(false)
  const reconnecting = ref(false)
  let ws: WebSocket | null = null
  let reconnectCount = 0

  function connect(): void {
    ws = new WebSocket(options.url)
    ws.onopen = () => { connected.value = true; reconnectCount = 0 }
    ws.onmessage = (e) => options.onMessage(JSON.parse(e.data) as T)
    ws.onclose = () => {
      connected.value = false
      if (reconnectCount < (options.maxReconnectAttempts ?? 5)) {
        reconnecting.value = true
        setTimeout(connect, options.reconnectInterval ?? 2000)
        reconnectCount++
      }
    }
    if (options.onError) ws.onerror = options.onError
  }

  function send(data: unknown): void {
    ws?.send(JSON.stringify(data))
  }

  function close(): void {
    reconnectCount = Infinity   // prevent reconnect
    ws?.close()
  }

  connect()
  onUnmounted(close)

  return { connected, reconnecting, send, close }
}
```

Usage in a page:

```typescript
const { connected, send } = useWebSocket<ScanEvent>({
  url: `ws://127.0.0.1:8000/ws/scan/${scanId}`,
  onMessage(event) {
    switch (event.type) {
      case 'progress': scanStore.updateProgress(event); break
      case 'error':    scanStore.addError(event); break
      case 'complete': scanStore.setComplete(event); break
    }
  },
})

// Cancel scan
function cancelScan() { send({ type: 'cancel' }) }
```

### useApi

```typescript
// composables/useApi.ts
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

interface ApiOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | undefined>
  signal?: AbortSignal
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (options.params) {
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), {
    method: options.method ?? 'GET',
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, detail.detail ?? 'Unknown error')
  }
  return res.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}
```

---

## Pinia Store Patterns

### Store Structure Convention

```typescript
// stores/scan.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/composables/useApi'
import type { ScanRun, TickerScore, PaginatedResponse } from '@/types'

export const useScanStore = defineStore('scan', () => {
  // --- State ---
  const scans = ref<ScanRun[]>([])
  const currentScanId = ref<number | null>(null)
  const scores = ref<TickerScore[]>([])
  const progress = ref<{ phase: string; current: number; total: number } | null>(null)
  const loading = ref(false)
  const errors = ref<Array<{ ticker: string; message: string }>>([])

  // --- Getters (computed) ---
  const latestScan = computed(() => scans.value[0] ?? null)
  const isScanning = computed(() => progress.value !== null)

  // --- Actions ---
  async function fetchScans(limit = 10): Promise<void> {
    loading.value = true
    try {
      scans.value = await api<ScanRun[]>('/api/scan', { params: { limit } })
    } finally {
      loading.value = false
    }
  }

  async function fetchScores(scanId: number): Promise<void> {
    loading.value = true
    try {
      const res = await api<PaginatedResponse<TickerScore>>(
        `/api/scan/${scanId}/scores`
      )
      scores.value = res.items
    } finally {
      loading.value = false
    }
  }

  // WebSocket callbacks (called from composable)
  function updateProgress(event: { phase: string; current: number; total: number }): void {
    progress.value = event
  }
  function addError(event: { ticker: string; message: string }): void {
    errors.value.push(event)
  }
  function setComplete(event: { scan_id: number; cancelled: boolean }): void {
    progress.value = null
    currentScanId.value = event.scan_id
  }

  return {
    scans, currentScanId, scores, progress, loading, errors,
    latestScan, isScanning,
    fetchScans, fetchScores, updateProgress, addError, setComplete,
  }
})
```

**Rules:**
- Always use **setup store syntax** (`defineStore('name', () => {...})`), never the options syntax.
- State: `ref()`. Getters: `computed()`. Actions: plain `async function`.
- Stores never import other stores (no circular deps). If two stores need to communicate,
  do it in the page component.
- Loading/error state lives in the store, not in page components.

---

## Styling Conventions

### Approach: PrimeVue Aura Dark + CSS Custom Properties

PrimeVue provides the base component styling via the Aura dark theme preset. Custom
components use scoped CSS + CSS custom properties for accent colors.

```typescript
// main.ts — PrimeVue theme setup
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import ToastService from 'primevue/toastservice'

app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      prefix: 'p',
      darkModeSelector: '.dark-mode',
      cssLayer: false,
    }
  }
})
app.use(ToastService)
```

Global accent overrides in `src/assets/variables.css`:

```css
:root {
  /* Financial accent colors (override PrimeVue defaults) */
  --accent-green: #22c55e;        /* green-500 (bullish) */
  --accent-red: #ef4444;          /* red-500 (bearish) */
  --accent-yellow: #eab308;       /* yellow-500 (neutral) */
  --accent-blue: #3b82f6;         /* blue-500 (risk agent) */
  --accent-purple: #a855f7;       /* purple-500 (volatility agent) */
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
}
```

Custom component styling:
```vue
<style scoped>
.agent-card {
  border-left: 4px solid var(--agent-color);
  padding: 1rem;
  border-radius: 0.5rem;
}
</style>
```

**Rules:**
- Dark theme by default (financial tools convention — easier on the eyes during market hours).
- PrimeVue Aura dark preset for all standard components. Never override PrimeVue internal CSS.
- Custom accent colors via CSS custom properties. No hardcoded hex in component `<style>` blocks.
- Use `scoped` on every custom component `<style>` tag.
- Numeric data uses `font-mono`. Text uses PrimeVue's default font stack.
- `<body class="dark-mode">` set in `index.html` for PrimeVue dark mode selector.

---

## Vite Configuration

```typescript
// vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws':  { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
```

**Dev mode**: Vite proxies `/api/*` and `/ws/*` to the FastAPI backend. No CORS issues in dev.

**Production**: FastAPI serves `web/dist/` via `StaticFiles`. Single process, single port.

---

## Formatting & Number Display Rules

Financial data has specific display conventions:

| Data Type | Format | Example |
|-----------|--------|---------|
| Prices (strike, bid, ask) | USD currency, 2dp | `$145.50` |
| Composite score | 1 decimal place | `7.3` |
| Sub-scores (momentum, value) | 1 decimal place | `6.8` |
| Confidence | Percentage, 0dp | `72%` |
| Greeks (delta, gamma) | 4 decimal places | `0.4523` |
| Greeks (theta) | 4dp, always negative | `-0.0234` |
| IV (implied volatility) | Percentage, 1dp | `34.2%` |
| Volume, open interest | Thousands separator | `1,500` |
| DTE (days to expiration) | Integer, "d" suffix | `45d` |
| Dates | Short format | `Mar 15, 2026` |
| Timestamps | Relative when < 24h | `2 hours ago` |

**Direction badges:**
- Bullish → green background, white text
- Bearish → red background, white text
- Neutral → yellow background, dark text

---

## Testing Patterns

### Framework

- **Vitest** for unit tests (Vite-native, same config)
- **Vue Test Utils** for component mounting
- **MSW (Mock Service Worker)** for API mocking in tests

### Test Structure

```
web/
    src/
        __tests__/               # Co-located with src/
            stores/
                scan.test.ts     # Store actions, state transitions
                debate.test.ts
            composables/
                useWebSocket.test.ts
                useApi.test.ts
            components/
                DataTable.test.ts
                AgentCard.test.ts
                ConfidenceBadge.test.ts
            pages/
                ScanResultsPage.test.ts
```

### What to Test

- **Stores**: state transitions, API call integration (with MSW mocks), computed getters
- **Composables**: `useWebSocket` reconnect logic, `useApi` error handling, abort behavior
- **Components**: prop rendering, event emissions, conditional display (loading, empty, error states)
- **DataTable**: sort behavior, filter behavior, pagination math

### What NOT to Test

- Exact CSS/styling (fragile, changes with design iteration)
- Vue Router navigation (test at page level with mocked router, not integration)
- WebSocket server behavior (tested in Python backend tests)
- Generated OpenAPI client code (generated, not hand-written)

### Component Test Pattern

```typescript
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ConfidenceBadge from '@/components/ConfidenceBadge.vue'

describe('ConfidenceBadge', () => {
  it('renders confidence as percentage', () => {
    const wrapper = mount(ConfidenceBadge, { props: { value: 0.72 } })
    expect(wrapper.text()).toContain('72%')
  })

  it('applies high-confidence style above 0.7', () => {
    const wrapper = mount(ConfidenceBadge, { props: { value: 0.85 } })
    expect(wrapper.classes()).toContain('confidence--high')
  })
})
```

---

## What Claude Gets Wrong -- Web-Specific (Fix These)

1. **Parsing price strings to `number`** — Prices arrive as JSON strings (`"145.50"`) from
   Pydantic's `@field_serializer`. Never `parseFloat()` them for storage or computation.
   Use `Number()` only inside display formatting functions. Precision loss is unacceptable.

2. **Options API or `defineComponent()`** — Always `<script setup lang="ts">`. The Composition
   API with `<script setup>` is the project standard. Never use Options API, `mixins`, or
   `defineComponent()` with a `setup()` return object.

3. **`any` type** — Never use `any`. Use the discriminated union types from `types/ws.ts` for
   WebSocket events. Use generated interfaces from OpenAPI for API responses. When truly
   unknown, use `unknown` with type guards.

4. **Global CSS without `scoped`** — Every component `<style>` block must have `scoped`. Only
   `variables.css` and `reset.css` are global. Leaking styles between components causes
   debugging nightmares.

5. **Storing WebSocket in reactive state** — `WebSocket` instances are not serializable. Store
   connection *status* (`connected`, `reconnecting`) as `ref<boolean>`, not the socket itself.

6. **Mutating store state outside actions** — Never `scanStore.scores.value.push(x)` from a
   component. Always call a store action: `scanStore.addScore(x)`. Actions are the only
   mutation path.

7. **Hardcoded `localhost:8000`** — Use `import.meta.env.VITE_API_URL` with a fallback. In dev,
   Vite's proxy handles routing. In production, the SPA is served from the same origin.

8. **Forgetting null checks on optional fields** — Many model fields are `T | null` (`Greeks`,
   `vol_response`, `bull_rebuttal`). Always null-check before rendering. Use `v-if` or
   `?? '--'` fallback, never let `null` render as the string `"null"`.

9. **Eager-loading all pages** — Use `() => import(...)` for route components. Eager imports
   increase initial bundle size. Only `App.vue` and the router are loaded eagerly.

10. **Math on DTE/scores in the frontend** — All computation (scoring, Greeks, indicators)
    happens in the Python backend. The frontend only *displays* numbers. If you need a derived
    value, add it to the backend API response.

11. **Missing `key` on `v-for` lists** — Every `v-for` must have a `:key` bound to a stable
    unique identifier (e.g., `ticker`, `id`). Never use array index as key.

12. **WebSocket without cleanup** — Always close WebSocket connections in `onUnmounted()`. The
    `useWebSocket` composable handles this, but if you use raw `WebSocket`, you must clean up
    manually. Leaked connections cause memory leaks and stale event handlers.

13. **Importing from `@/pages/` in a component** — Components never import pages. The dependency
    direction is: pages → components → composables/stores. Never reverse this.

14. **`Optional<X>` in TypeScript** — This is the Python convention (`X | None`). In TypeScript,
    use `T | null` for nullable values and `T | undefined` (or `?:`) for optional props.
    Don't confuse the two — `null` means "no value from API", `undefined` means "prop not passed".
