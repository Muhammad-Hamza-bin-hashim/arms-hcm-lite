const DATE = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
const SHORT = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short' })
const TIME = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })
const DATETIME = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric' })

/** Parses 'YYYY-MM-DD' as a local calendar date (no timezone shift). */
export function parseDate(d: string) {
  const [y, m, day] = d.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, day)
}

export const fmtDate = (d?: string | null) => (d ? DATE.format(d.length <= 10 ? parseDate(d) : new Date(d)) : '—')
export const fmtShort = (d?: string | null) => (d ? SHORT.format(d.length <= 10 ? parseDate(d) : new Date(d)) : '—')
export const fmtTime = (d?: string | null) => (d ? TIME.format(new Date(d)) : '—')
export const fmtDateTime = (d?: string | null) => (d ? DATETIME.format(new Date(d)) : '—')
export const fmtMonth = (period: string) => MONTH.format(parseDate(`${period}-01`))

export function fmtMoney(v?: string | number | null, currency = 'PKR') {
  if (v === null || v === undefined || v === '') return '—'
  const n = typeof v === 'string' ? Number(v) : v
  return `${currency} ${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

export function fmtNumber(v?: string | number | null, digits = 0) {
  if (v === null || v === undefined || v === '') return '—'
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })
}

export const fmtPct = (v?: number | null) => (v === null || v === undefined ? '—' : `${v}%`)

export function fmtMinutes(m?: number | null) {
  if (m === null || m === undefined) return '—'
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

export function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export const today = () => isoDate(new Date())
export const monthStart = () => { const d = new Date(); return isoDate(new Date(d.getFullYear(), d.getMonth(), 1)) }

export const label = (s?: string | null) => (s ? s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()) : '—')

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
