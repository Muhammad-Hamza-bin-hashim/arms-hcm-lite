import { useMutation, useQuery } from '@tanstack/react-query'
import { Megaphone, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { fmtDateTime, isoDate, monthStart, today } from '../lib/format'
import { useDepartments } from '../lib/queries'
import type { Announcement, Page } from '../lib/types'
import { Link } from 'react-router-dom'
import { AIBadge, Alert, Badge, Button, Card, EmptyState, Skeleton } from './ui'

export interface Filters { from: string; to: string; department: string }
export const defaultFilters = (): Filters => ({ from: monthStart(), to: today(), department: '' })

export function FilterBar({ value, onChange }: { value: Filters; onChange: (f: Filters) => void }) {
  const { data: depts } = useDepartments()
  const presets = [
    { label: 'This month', from: monthStart(), to: today() },
    { label: 'Last 7 days', from: isoDate(new Date(Date.now() - 6 * 864e5)), to: today() },
    { label: 'Year to date', from: `${new Date().getFullYear()}-01-01`, to: today() },
  ]
  const cls = 'h-9 rounded-lg border border-line bg-surface px-2.5 text-sm focus:border-teal focus:outline-none'
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface p-2.5">
      <div className="flex gap-1">
        {presets.map((p) => (
          <button key={p.label} onClick={() => onChange({ ...value, from: p.from, to: p.to })}
            className={`h-8 rounded-lg px-2.5 text-xs font-medium ${value.from === p.from && value.to === p.to ? 'bg-teal-soft text-teal' : 'text-muted hover:bg-surface-2'}`}>
            {p.label}
          </button>
        ))}
      </div>
      <label className="sr-only" htmlFor="f-from">From</label>
      <input id="f-from" type="date" className={cls} value={value.from} max={value.to} onChange={(e) => e.target.value && onChange({ ...value, from: e.target.value })} />
      <span className="text-xs text-muted">to</span>
      <label className="sr-only" htmlFor="f-to">To</label>
      <input id="f-to" type="date" className={cls} value={value.to} min={value.from} onChange={(e) => e.target.value && onChange({ ...value, to: e.target.value })} />
      <label className="sr-only" htmlFor="f-dept">Department</label>
      <select id="f-dept" className={cls} value={value.department} onChange={(e) => onChange({ ...value, department: e.target.value })}>
        <option value="">All departments</option>
        {depts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </select>
    </div>
  )
}

export function AISummary({ filters, board }: { filters: Filters; board: 'admin' | 'hr' }) {
  const m = useMutation({
    mutationFn: () => api.post<{ ok: boolean; bullets: string[]; error: string | null }>('/ai/summary/', { ...filters, dashboard: board }),
  })
  return (
    <Card title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-violet" /> AI summary</span>}
      action={<Button size="sm" variant="secondary" onClick={() => m.mutate()} loading={m.isPending}>{m.data ? 'Refresh' : 'Summarize'}</Button>}>
      {!m.data && !m.isPending && !m.error && <p className="text-sm text-muted">Get 3–5 insights written from the KPIs for the current filters. Only these numbers are used.</p>}
      {m.isPending && <div className="space-y-2"><Skeleton className="h-4" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-4/6" /></div>}
      {m.error && <Alert>{(m.error as Error).message}</Alert>}
      {m.data && !m.data.ok && <Alert tone="amber">{m.data.error} The dashboard numbers above are still accurate.</Alert>}
      {m.data?.ok && (
        <>
          <ul className="list-disc space-y-1.5 pl-5 text-sm">{m.data.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
          <div className="mt-3"><AIBadge /></div>
        </>
      )}
    </Card>
  )
}

export function AnnouncementsCard({ limit = 3 }: { limit?: number }) {
  const { data, isLoading } = useQuery({ queryKey: ['announcements'], queryFn: () => api.get<Page<Announcement>>('/announcements/') })
  return (
    <Card title={<span className="flex items-center gap-2"><Megaphone className="size-4 text-amber" /> Announcements</span>}>
      {isLoading && <Skeleton className="h-16" />}
      {data && !data.results.length && <EmptyState title="No announcements yet" />}
      <ul className="space-y-3">
        {data?.results.slice(0, limit).map((a) => (
          <li key={a.id} className="border-b border-line pb-3 last:border-0 last:pb-0">
            <p className="text-sm font-medium">{a.title}</p>
            <p className="mt-0.5 line-clamp-3 text-sm whitespace-pre-line text-muted">{a.body}</p>
            <p className="mt-1 text-[11px] text-muted">{a.created_by_name} · {fmtDateTime(a.created_at)}</p>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export interface Insights {
  attrition_risk: { employee_id: number; code: string; name: string; department: string; score: number; level: 'low' | 'medium' | 'high'; reasons: string[] }[]
  risk_levels: { high: number; medium: number; low: number }
  anomalies: { type: string; severity: 'low' | 'medium' | 'high'; employee_id: number | null; name: string; department: string; detail: string }[]
}

const SEVERITY_TONE = { high: 'red', medium: 'amber', low: 'gray' } as const

/** Bonus insights: rule-based attrition risk (last 60 days) and absence anomaly flags. */
export function InsightsCard({ insights }: { insights: Insights }) {
  const { attrition_risk: risk, risk_levels: levels, anomalies } = insights
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card title="Attrition risk (last 60 days)"
        action={<span className="flex gap-1"><Badge tone="red">{levels.high} high</Badge><Badge tone="amber">{levels.medium} medium</Badge><Badge>{levels.low} low</Badge></span>}>
        {!risk.length ? <EmptyState title="No medium or high risk employees" body="Scores use absences, lateness, unpaid and rejected leave, tenure and probation." /> : (
          <ul className="space-y-3">
            {risk.map((r) => (
              <li key={r.employee_id} className="flex items-start gap-3">
                <span className={`tabular mt-0.5 w-10 shrink-0 rounded-md py-1 text-center text-xs font-semibold ${r.level === 'high' ? 'bg-red-soft text-red' : 'bg-amber-soft text-amber'}`}>{r.score}</span>
                <div className="min-w-0 text-sm">
                  <Link to={`/employees/${r.employee_id}`} className="font-medium hover:underline">{r.name}</Link>
                  <span className="text-muted"> · {r.department}</span>
                  <p className="text-xs text-muted">{r.reasons.join(' · ')}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[11px] text-muted">A transparent rule score from records, not a prediction. Use it as a prompt for a conversation.</p>
      </Card>
      <Card title="Absence anomaly flags">
        {!anomalies.length ? <EmptyState title="No unusual absence patterns" body="Checks: 3+ consecutive absences, Monday/Friday clustering, repeated missing check-outs, department spikes." /> : (
          <ul className="space-y-2.5">
            {anomalies.slice(0, 8).map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <Badge tone={SEVERITY_TONE[a.severity]}>{a.severity}</Badge>
                <div className="min-w-0">
                  {a.employee_id ? <Link to={`/employees/${a.employee_id}`} className="font-medium hover:underline">{a.name}</Link> : <span className="font-medium">{a.name} department</span>}
                  <p className="text-xs text-muted">{a.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
