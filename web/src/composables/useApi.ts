/** Typed fetch wrapper for API calls. */

/** Default request timeout in milliseconds (AUDIT-028). */
const DEFAULT_TIMEOUT_MS = 30_000

interface ApiOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | undefined>
  signal?: AbortSignal
  /** Request timeout in ms. Defaults to 30 000 (30 s). */
  timeout?: number
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (options.params) {
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined) url.searchParams.set(k, String(v))
    }
  }

  // Apply a default timeout via AbortController unless caller provides a signal
  const controller = new AbortController()
  const timeoutId = setTimeout(
    () => controller.abort(),
    options.timeout ?? DEFAULT_TIMEOUT_MS,
  )

  // If the caller already provided a signal, forward its abort to our controller
  if (options.signal) {
    options.signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const res = await fetch(url.toString(), {
      method: options.method ?? 'GET',
      headers: options.body ? { 'Content-Type': 'application/json' } : {},
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({ detail: res.statusText }))
      throw new ApiError(res.status, (detail as { detail?: string }).detail ?? 'Unknown error')
    }
    return res.json() as Promise<T>
  } finally {
    clearTimeout(timeoutId)
  }
}
