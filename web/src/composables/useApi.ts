/** Typed fetch wrapper for API calls. */

interface ApiOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  body?: unknown
  params?: Record<string, string | number | undefined>
  signal?: AbortSignal
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
  const res = await fetch(url.toString(), {
    method: options.method ?? 'GET',
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, (detail as { detail?: string }).detail ?? 'Unknown error')
  }
  return res.json() as Promise<T>
}
