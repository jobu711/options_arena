import type { ScanRun } from '@/types'

/** Format scan duration as human-readable string (e.g., "2m 15s", "45s", "--"). */
export function formatScanDuration(scan: ScanRun): string {
  if (!scan.completed_at || !scan.started_at) return '--'
  const ms = new Date(scan.completed_at).getTime() - new Date(scan.started_at).getTime()
  if (ms < 0) return '--'
  const totalSec = Math.round(ms / 1000)
  if (totalSec < 60) return `${totalSec}s`
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`
}

/** Format a Decimal-as-string price for display with currency symbol. Returns '--' for non-finite values. */
export function formatPrice(price: string): string {
  const num = Number(price)
  if (!Number.isFinite(num)) return '--'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

/** Format an ISO datetime string as a full localized datetime (e.g., "3/6/2026, 2:30:45 PM"). */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

/**
 * Format an ISO date-only string (e.g., "2026-03-21") as a localized date.
 * Parses year/month/day components directly to avoid UTC midnight timezone shift.
 */
export function formatDateOnly(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString()
}

/** Format an ISO date string as short date (e.g., "Mar 15, 2026"). */
export function formatDateShort(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Format an ISO date string as compact date for charts (e.g., "Mar 15"). */
export function formatDateCompact(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}
