import { describe, expect, it } from 'vitest'
import { qs } from './api'
import { fmtMinutes, fmtMoney, fmtPct, isoDate, label, parseDate } from './format'

describe('format helpers', () => {
  it('parses calendar dates without a timezone shift', () => {
    const d = parseDate('2026-10-26')
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 9, 26])
    expect(isoDate(d)).toBe('2026-10-26')
  })

  it('formats minutes, money, percentages and labels', () => {
    expect(fmtMinutes(485)).toBe('8h 05m')
    expect(fmtMinutes(null)).toBe('—')
    expect(fmtMoney('150000.00')).toBe('PKR 150,000')
    expect(fmtPct(null)).toBe('—')
    expect(fmtPct(87.5)).toBe('87.5%')
    expect(label('missing_checkout')).toBe('Missing checkout')
  })

  it('builds query strings and drops empty values', () => {
    expect(qs({ from: '2026-10-01', department: '', page: 2, x: undefined })).toBe('?from=2026-10-01&page=2')
    expect(qs({})).toBe('')
  })
})
