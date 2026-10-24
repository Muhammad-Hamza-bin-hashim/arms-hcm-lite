import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckInWidget } from '../../components/CheckInWidget'
import { useToast } from '../../components/toast'
import {
  Alert, Button, Card, cx, EmptyState, ErrorState, FilterSelect, IconButton, Input, Kpi, Modal, PageHeader, Pagination, Spinner,
  StatusBadge, Table, Tabs, Textarea,
} from '../../components/ui'
import { api, fieldError, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDate, fmtDateTime, fmtMinutes, fmtMonth, fmtPct, fmtTime, label, parseDate, today } from '../../lib/format'
import { useDepartments } from '../../lib/queries'
import type { AttendanceSummary, Page } from '../../lib/types'

interface BoardRow {
  employee_id: number; employee_code: string; name: string; department: string; status: string; leave_type: string | null
  is_late: boolean; check_in: string | null; check_out: string | null; worked_minutes: number | null; source: string | null
}

export function AttendanceBoardPage() {
  const { data: depts } = useDepartments()
  const [date, setDate] = useState(today())
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['attendance-board', date, department, status],
    queryFn: () => api.get<{ date: string; summary: AttendanceSummary; rows: BoardRow[] }>(`/attendance/board/${qs({ date, department, status })}`),
    placeholderData: (p) => p,
    refetchInterval: 60_000,
  })
  const s = data?.summary
  return (
    <>
      <PageHeader title="Daily attendance board" subtitle="Everyone's status for one day, including leave and absences." />
      <div className="mb-4 flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="board-date">Date</label>
        <input id="board-date" type="date" value={date} max={today()} onChange={(e) => e.target.value && setDate(e.target.value)}
          className="h-9 rounded-lg border border-line bg-surface px-2.5 text-sm" />
        <FilterSelect label="Department" value={department} onChange={setDepartment}>
          <option value="">All departments</option>{depts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </FilterSelect>
        <FilterSelect label="Status" value={status} onChange={setStatus}>
          <option value="">All statuses</option>
          {['present', 'late', 'half_day', 'missing_checkout', 'on_leave', 'absent', 'not_marked'].map((x) => <option key={x} value={x}>{label(x)}</option>)}
        </FilterSelect>
      </div>
      {error ? <ErrorState error={error} retry={refetch} /> : isLoading || !s ? <Spinner /> : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <Kpi label="Checked in" value={data.rows.filter((r) => r.check_in).length} />
            <Kpi label="Late arrivals" value={data.rows.filter((r) => r.is_late).length} tone="amber" />
            <Kpi label="Half day" value={s.half_day} tone="amber" />
            <Kpi label="On leave" value={s.on_leave} tone="blue" />
            <Kpi label={date === today() ? 'Not checked in' : 'Absent'} value={date === today() ? s.not_marked : s.absent} tone="red" />
            <Kpi label="Attendance rate" value={fmtPct(s.attendance_rate)} tone="violet" />
          </div>
          <Card>
            <Table rows={data.rows} rowKey={(r) => r.employee_id}
              empty={<EmptyState title="No employees for this day" body="Nobody was employed on this date, or the filters exclude everyone." />}
              columns={[
                { key: 'n', header: 'Employee', cell: (r) => <Link to={`/employees/${r.employee_id}`} className="hover:underline"><p className="font-medium">{r.name}</p><p className="text-xs text-muted">{r.employee_code}</p></Link> },
                { key: 'd', header: 'Department', cell: (r) => r.department },
                { key: 's', header: 'Status', cell: (r) => <div className="flex flex-wrap gap-1"><StatusBadge status={r.status} text={r.leave_type ? `On leave (${r.leave_type})` : undefined} />{r.is_late && r.status !== 'late' && <StatusBadge status="late" text="Late" />}</div> },
                { key: 'i', header: 'In', cell: (r) => <span className="tabular">{fmtTime(r.check_in)}</span> },
                { key: 'o', header: 'Out', cell: (r) => <span className="tabular">{fmtTime(r.check_out)}</span> },
                { key: 'w', header: 'Worked', cell: (r) => <span className="tabular">{fmtMinutes(r.worked_minutes)}</span> },
                { key: 'src', header: 'Source', cell: (r) => r.source ? label(r.source) : '—' },
              ]} />
          </Card>
        </>
      )}
    </>
  )
}

interface Correction {
  id: number; employee: number; employee_name: string; employee_code: string; date: string; check_in_time: string; check_out_time: string | null
  reason: string; status: string; reviewed_by_name: string | null; reviewed_at: string | null; review_comment: string; created_at: string
}

export function CorrectionsPage() {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const [status, setStatus] = useState<'pending' | ''>('pending')
  const [page, setPage] = useState(1)
  const [deciding, setDeciding] = useState<{ c: Correction; approve: boolean } | null>(null)
  const [comment, setComment] = useState('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['corrections', status, page],
    queryFn: () => api.get<Page<Correction>>(`/attendance/corrections/${qs({ status, page })}`),
  })
  const decide = useMutation({
    mutationFn: ({ c, approve }: { c: Correction; approve: boolean }) => api.post(`/attendance/corrections/${c.id}/${approve ? 'approve' : 'reject'}/`, { comment }),
    onSuccess: (_, v) => { setDeciding(null); setComment(''); qc.invalidateQueries({ queryKey: ['corrections'] }); qc.invalidateQueries({ queryKey: ['attendance-board'] }); toast.success(`Correction ${v.approve ? 'approved' : 'rejected'}.`) },
    onError: toast.error,
  })
  const canDecide = user.role === 'hr'
  return (
    <>
      <PageHeader title="Attendance corrections" subtitle={canDecide ? 'Approve or reject requests to fix missed or wrong check-ins.' : 'Requests and HR decisions (view only).'} />
      <Tabs value={status} onChange={(v) => { setStatus(v); setPage(1) }} tabs={[{ id: 'pending', label: 'Pending' }, { id: '', label: 'All' }]} />
      <Card>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(c) => c.id}
              empty={<EmptyState title={status ? 'No pending corrections' : 'No correction requests yet'} />}
              columns={[
                { key: 'e', header: 'Employee', cell: (c) => <div><p className="font-medium">{c.employee_name}</p><p className="text-xs text-muted">{c.employee_code}</p></div> },
                { key: 'd', header: 'Date', cell: (c) => fmtDate(c.date) },
                { key: 't', header: 'Requested times', cell: (c) => <span className="tabular">{c.check_in_time.slice(0, 5)} – {c.check_out_time?.slice(0, 5) ?? 'no checkout'}</span> },
                { key: 'r', header: 'Reason', cell: (c) => <p className="max-w-xs text-sm">{c.reason}</p> },
                { key: 's', header: 'Status', cell: (c) => <div><StatusBadge status={c.status} />{c.review_comment && <p className="mt-1 text-xs text-muted">“{c.review_comment}”</p>}</div> },
                ...(canDecide ? [{ key: 'a', header: '', className: 'text-right', cell: (c: Correction) => c.status === 'pending' && (
                  <div className="flex justify-end gap-1">
                    <IconButton label="Approve" className="hover:text-teal" onClick={() => setDeciding({ c, approve: true })}><Check className="size-4" /></IconButton>
                    <IconButton label="Reject" className="hover:text-red" onClick={() => setDeciding({ c, approve: false })}><X className="size-4" /></IconButton>
                  </div>) }] : []),
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={deciding !== null} onClose={() => setDeciding(null)} title={deciding?.approve ? 'Approve correction' : 'Reject correction'}
        footer={<><Button variant="secondary" onClick={() => setDeciding(null)}>Cancel</Button>
          <Button variant={deciding?.approve ? 'success' : 'danger'} loading={decide.isPending} onClick={() => deciding && decide.mutate(deciding)}>{deciding?.approve ? 'Approve' : 'Reject'}</Button></>}>
        {deciding && (
          <div className="space-y-3 text-sm">
            <p><b>{deciding.c.employee_name}</b> · {fmtDate(deciding.c.date)} · {deciding.c.check_in_time.slice(0, 5)} – {deciding.c.check_out_time?.slice(0, 5) ?? 'no checkout'}</p>
            <p className="text-muted">{deciding.c.reason}</p>
            {deciding.approve && <Alert tone="blue">Approving creates or replaces that day's record with these times.</Alert>}
            <Textarea label="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} />
          </div>
        )}
      </Modal>
    </>
  )
}

interface CalendarDay { date: string; status: string; leave_type: string | null; is_late: boolean; working: boolean; holiday: boolean; check_in: string | null; check_out: string | null; worked_minutes: number | null }

const CELL: Record<string, string> = {
  present: 'bg-teal-soft text-teal', late: 'bg-amber-soft text-amber', half_day: 'bg-amber-soft text-amber', missing_checkout: 'bg-violet-soft text-violet',
  on_leave: 'bg-blue-soft text-blue', absent: 'bg-red-soft text-red', not_marked: 'border border-dashed border-line text-muted',
}

export function MyAttendancePage() {
  const now = new Date()
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [requestOpen, setRequestOpen] = useState(false)
  const [prefillDate, setPrefillDate] = useState('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['my-calendar', month],
    queryFn: () => api.get<{ month: string; summary: AttendanceSummary; days: CalendarDay[] }>(`/attendance/calendar/?month=${month}`),
  })
  const shift = (delta: number) => {
    const [y, m] = month.split('-').map(Number)
    const d = new Date(y, m - 1 + delta, 1)
    setMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)
  }
  const first = data?.days[0] ? (parseDate(data.days[0].date).getDay() + 6) % 7 : 0
  return (
    <>
      <PageHeader title="My attendance" subtitle="Your calendar, hours and correction requests."
        actions={<Button variant="secondary" onClick={() => { setPrefillDate(''); setRequestOpen(true) }}><Plus className="size-4" /> Request correction</Button>} />
      <div className="space-y-5">
        <CheckInWidget />
        <Card title={<span className="flex items-center gap-2">
          <IconButton label="Previous month" onClick={() => shift(-1)}><ChevronLeft className="size-4" /></IconButton>
          <span className="min-w-36 text-center">{fmtMonth(month)}</span>
          <IconButton label="Next month" onClick={() => shift(1)}><ChevronRight className="size-4" /></IconButton>
        </span>}>
          {error ? <ErrorState error={error} retry={refetch} /> : isLoading || !data ? <Spinner /> : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Kpi label="Attendance rate" value={fmtPct(data.summary.attendance_rate)} />
                <Kpi label="Late arrivals" value={data.summary.late_arrivals} tone="amber" />
                <Kpi label="Half days" value={data.summary.half_day} tone="amber" />
                <Kpi label="On leave" value={data.summary.on_leave} tone="blue" />
                <Kpi label="Absent" value={data.summary.absent} tone="red" />
              </div>
              <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-medium text-muted">
                {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="py-1">{d}</div>)}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {Array.from({ length: first }, (_, i) => <div key={`pad${i}`} />)}
                {data.days.map((d) => {
                  const day = parseDate(d.date).getDate()
                  const canFix = ['absent', 'missing_checkout', 'late', 'half_day'].includes(d.status)
                  return (
                    <button key={d.date} type="button" disabled={!canFix}
                      onClick={() => { setPrefillDate(d.date); setRequestOpen(true) }}
                      title={`${fmtDate(d.date)}: ${d.holiday ? 'Holiday' : label(d.status)}${d.check_in ? ` · ${fmtTime(d.check_in)}–${fmtTime(d.check_out)}` : ''}`}
                      className={cx('flex min-h-14 flex-col items-start rounded-lg p-1.5 text-left text-xs sm:min-h-16',
                        CELL[d.status] ?? 'bg-surface-2 text-muted', canFix && 'cursor-pointer hover:ring-2 hover:ring-teal/40')}>
                      <span className="font-semibold">{day}</span>
                      <span className="mt-auto hidden truncate sm:block">{d.holiday ? 'Holiday' : ['weekend', 'future', 'not_employed'].includes(d.status) ? '' : d.leave_type ? label(d.leave_type) : label(d.status)}</span>
                      {d.check_in && <span className="tabular hidden text-[10px] opacity-80 md:block">{fmtTime(d.check_in)}</span>}
                    </button>
                  )
                })}
              </div>
              <p className="mt-3 text-xs text-muted">Click a late, half-day, absent or missing-checkout day to request a correction.</p>
            </>
          )}
        </Card>
        <MyCorrections />
      </div>
      <CorrectionRequest open={requestOpen} onClose={() => setRequestOpen(false)} date={prefillDate} />
    </>
  )
}

function MyCorrections() {
  const { data, isLoading } = useQuery({ queryKey: ['corrections', 'mine'], queryFn: () => api.get<Page<Correction>>('/attendance/corrections/?mine=true') })
  return (
    <Card title="My correction requests">
      {isLoading ? <Spinner /> : (
        <Table rows={data?.results ?? []} rowKey={(c) => c.id} empty={<EmptyState title="No correction requests" />}
          columns={[
            { key: 'd', header: 'Date', cell: (c) => fmtDate(c.date) },
            { key: 't', header: 'Times', cell: (c) => `${c.check_in_time.slice(0, 5)} – ${c.check_out_time?.slice(0, 5) ?? '—'}` },
            { key: 'r', header: 'Reason', cell: (c) => c.reason },
            { key: 's', header: 'Status', cell: (c) => <StatusBadge status={c.status} /> },
            { key: 'c', header: 'HR comment', cell: (c) => c.review_comment || (c.reviewed_at ? '—' : `Sent ${fmtDateTime(c.created_at)}`) },
          ]} />
      )}
    </Card>
  )
}

function CorrectionRequest({ open, onClose, date }: { open: boolean; onClose: () => void; date: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ date: '', check_in_time: '09:00', check_out_time: '18:00', reason: '' })
  const [lastDate, setLastDate] = useState<string | null>(null)
  if (open && lastDate !== date) { setLastDate(date); setForm((f) => ({ ...f, date: date || today() })) }
  if (!open && lastDate !== null) setLastDate(null)
  const m = useMutation({
    mutationFn: () => api.post('/attendance/corrections/', { ...form, check_out_time: form.check_out_time || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['corrections'] }); onClose(); toast.success('Correction sent to HR.') },
  })
  const fe = (k: string) => fieldError(m.error, k)
  return (
    <Modal open={open} onClose={onClose} title="Request attendance correction"
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={m.isPending} onClick={() => m.mutate()}>Send to HR</Button></>}>
      <form className="grid gap-4 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); m.mutate() }}>
        <Input label="Date" type="date" required max={today()} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} error={fe('date')} />
        <Input label="Check in" type="time" required value={form.check_in_time} onChange={(e) => setForm({ ...form, check_in_time: e.target.value })} error={fe('check_in_time')} />
        <Input label="Check out" type="time" value={form.check_out_time} onChange={(e) => setForm({ ...form, check_out_time: e.target.value })} error={fe('check_out_time')} />
        <div className="sm:col-span-3"><Textarea label="Reason" required value={form.reason} maxLength={1000} onChange={(e) => setForm({ ...form, reason: e.target.value })} error={fe('reason')} placeholder="e.g. Forgot to check out after a client meeting" /></div>
        {m.error && !['date', 'check_in_time', 'check_out_time', 'reason'].some(fe) && <div className="sm:col-span-3"><Alert>{(m.error as Error).message}</Alert></div>}
        <button type="submit" hidden />
      </form>
    </Modal>
  )
}
