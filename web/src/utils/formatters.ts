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

/** Format a Decimal-as-string price for display with currency symbol. */
export function formatPrice(price: string): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(price))
}
