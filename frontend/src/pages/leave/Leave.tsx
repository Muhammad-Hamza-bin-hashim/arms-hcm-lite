import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Sparkles, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useToast } from '../../components/toast'
import {
  AIBadge, Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, FilterSelect, IconButton, Input, Modal, PageHeader,
  Pagination, Select, Spinner, StatusBadge, Table, Tabs, Textarea,
} from '../../components/ui'
import { api, ApiError, fieldError, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDate, fmtDateTime, today } from '../../lib/format'
import { useDepartments, useLeaveTypeOptions } from '../../lib/queries'
import type { Balance, LeaveRequest, Page } from '../../lib/types'

type Draft = { leave_type: string; start_date: string; end_date: string; reason: string; source: 'form' | 'ai' }
const blankDraft = (): Draft => ({ leave_type: 'casual', start_date: '', end_date: '', reason: '', source: 'form' })

export function MyLeavePage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: types } = useLeaveTypeOptions()
  const [draft, setDraft] = useState<Draft>(blankDraft)
  const [smartText, setSmartText] = useState('')
  const [smartNote, setSmartNote] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState<LeaveRequest | null>(null)
  const [preview, setPreview] = useState<{ days?: number; error?: string } | null>(null)
  const [page, setPage] = useState(1)

  const balance = useQuery({ queryKey: ['leave-balance'], queryFn: () => api.get<{ year: number; balances: Balance[] }>('/leave/balance/') })
  const history = useQuery({ queryKey: ['my-leave', page], queryFn: () => api.get<Page<LeaveRequest>>(`/leave/requests/?mine=true&page=${page}`) })

  // Live validation using the same backend rules as the real submission.
  useEffect(() => {
    if (!draft.leave_type || !draft.start_date || !draft.end_date) { setPreview(null); return }
    const t = setTimeout(() => {
      api.post<{ days: number }>('/leave/preview/', draft).then((r) => setPreview({ days: r.days }))
        .catch((e) => setPreview({ error: e instanceof Error ? e.message : 'Invalid' }))
    }, 350)
    return () => clearTimeout(t)
  }, [draft])

  const smart = useMutation({
    mutationFn: () => api.post<{ ok: boolean; fallback?: boolean; error?: string; draft?: { leave_type: string; start_date: string; end_date: string; reason: string }; days?: number; validation_error?: string | null }>('/ai/smart-leave/', { text: smartText }),
    onSuccess: (r) => {
      if (r.ok && r.draft) {
        setDraft({ ...r.draft, source: 'ai' })
        setSmartNote(r.validation_error ? `Pre-filled, but: ${r.validation_error}` : `Pre-filled ${r.days} working day(s). Review and submit.`)
      } else setSmartNote(`${r.error ?? 'The assistant could not read that.'} Please fill the form below.`)
    },
    onError: (e) => setSmartNote(`${e instanceof Error ? e.message : 'AI unavailable.'} Please fill the form below.`),
  })
  const apply = useMutation({
    mutationFn: () => api.post<LeaveRequest>('/leave/requests/', draft),
    onSuccess: () => {
      setDraft(blankDraft()); setSmartText(''); setSmartNote(null); setPreview(null)
      ;['my-leave', 'leave-balance', 'employee-dashboard'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast.success('Leave request sent to HR.')
    },
  })
  const cancel = useMutation({
    mutationFn: (lr: LeaveRequest) => api.post(`/leave/requests/${lr.id}/cancel/`),
    onSuccess: () => { setCancelling(null); ['my-leave', 'leave-balance'].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); toast.success('Leave cancelled.') },
    onError: (e) => { setCancelling(null); toast.error(e) },
  })
  const fe = (k: string) => fieldError(apply.error, k)
  const set = (k: keyof Draft) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [k]: e.target.value }))

  return (
    <>
      <PageHeader title="My leave" subtitle="Leave counts working days only — weekends and public holidays are skipped." />
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {balance.isLoading && <Spinner />}
        {balance.data?.balances.map((b) => (
          <div key={b.code} className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs font-medium text-muted">{b.name}{!b.is_paid && ' (unpaid)'}</p>
            <p className="tabular mt-2 text-2xl font-semibold">{b.remaining ?? '∞'}<span className="text-sm font-normal text-muted">{b.quota !== null && ` / ${b.quota}`}</span></p>
            <p className="mt-1 text-xs text-muted">{b.used} used{b.pending ? ` · ${b.pending} pending` : ''}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-2">
          <Card title={<span className="flex items-center gap-2"><Sparkles className="size-4 text-violet" /> Smart leave</span>}>
            <form onSubmit={(e) => { e.preventDefault(); if (smartText.trim()) smart.mutate() }} className="space-y-3">
              <Textarea label="Describe your leave in plain words" value={smartText} onChange={(e) => setSmartText(e.target.value)} maxLength={500}
                placeholder="e.g. Need next Monday and Tuesday off for my sister's wedding" />
              <Button type="submit" variant="secondary" loading={smart.isPending} disabled={!smartText.trim()}>Fill the form for me</Button>
              {smartNote && <Alert tone={draft.source === 'ai' ? 'teal' : 'amber'}>{smartNote}</Alert>}
              <p className="text-xs text-muted">The assistant only pre-fills the form. Nothing is submitted until you press Submit.</p>
            </form>
          </Card>
          <Card title={<span className="flex items-center gap-2">Apply for leave {draft.source === 'ai' && <AIBadge />}</span>}>
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); apply.mutate() }}>
              <Select label="Leave type" required value={draft.leave_type} onChange={set('leave_type')} error={fe('leave_type')}>
                {types?.map((t) => <option key={t.code} value={t.code}>{t.name}{t.yearly_quota === null ? ' (unlimited)' : ''}</option>)}
              </Select>
              <div className="grid grid-cols-2 gap-3">
                <Input label="From" type="date" required value={draft.start_date} onChange={set('start_date')} error={fe('start_date')} />
                <Input label="To" type="date" required min={draft.start_date} value={draft.end_date} onChange={set('end_date')} error={fe('end_date')} />
              </div>
              <Textarea label="Reason" required value={draft.reason} onChange={set('reason')} maxLength={500} error={fe('reason')} />
              {preview?.days !== undefined && <Alert tone="teal">{preview.days} working day(s). Balance and overlap checks passed.</Alert>}
              {preview?.error && <Alert tone="amber">{preview.error}</Alert>}
              {apply.error && !(apply.error instanceof ApiError && apply.error.errors && Object.keys(apply.error.errors).some((k) => fe(k))) && <Alert>{(apply.error as Error).message}</Alert>}
              <div className="flex gap-2">
                <Button type="submit" loading={apply.isPending}>Submit request</Button>
                {(draft.start_date || draft.reason) && <Button type="button" variant="ghost" onClick={() => { setDraft(blankDraft()); setSmartNote(null); apply.reset() }}>Clear</Button>}
              </div>
            </form>
          </Card>
        </div>
        <Card title="My requests" className="lg:col-span-3">
          {history.error ? <ErrorState error={history.error} retry={history.refetch} /> : history.isLoading ? <Spinner /> : (
            <>
              <Table rows={history.data?.results ?? []} rowKey={(r) => r.id} empty={<EmptyState title="No leave requests yet" />}
                columns={[
                  { key: 't', header: 'Type', cell: (r) => <div className="flex items-center gap-1.5">{r.leave_type_name}{r.source === 'ai' && <Badge tone="violet">AI</Badge>}</div> },
                  { key: 'd', header: 'Dates', cell: (r) => <span className="whitespace-nowrap">{fmtDate(r.start_date)}{r.end_date !== r.start_date && ` – ${fmtDate(r.end_date)}`}</span> },
                  { key: 'n', header: 'Days', cell: (r) => r.days },
                  { key: 's', header: 'Status', cell: (r) => <div><StatusBadge status={r.status} />{r.decision_comment && <p className="mt-1 max-w-48 text-xs text-muted">“{r.decision_comment}”</p>}</div> },
                  { key: 'a', header: '', className: 'text-right', cell: (r) => (r.status === 'pending' || (r.status === 'approved' && r.start_date > today())) && (
                    <Button size="sm" variant="ghost" onClick={() => setCancelling(r)}>Cancel</Button>) },
                ]} />
              <Pagination page={page} count={history.data?.count ?? 0} onPage={setPage} />
            </>
          )}
        </Card>
      </div>
      <ConfirmDialog open={cancelling !== null} onClose={() => setCancelling(null)} title="Cancel leave request?" tone="danger" confirmLabel="Cancel leave"
        loading={cancel.isPending} onConfirm={() => cancelling && cancel.mutate(cancelling)}
        body={cancelling && <>{cancelling.leave_type_name} leave, {fmtDate(cancelling.start_date)} – {fmtDate(cancelling.end_date)} ({cancelling.days} days). The days return to your balance.</>} />
    </>
  )
}

export function LeaveRequestsPage() {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const [params] = useSearchParams()
  const { data: depts } = useDepartments()
  const { data: types } = useLeaveTypeOptions()
  const [status, setStatus] = useState<string>(params.get('status') ?? 'pending')
  const [department, setDepartment] = useState('')
  const [leaveType, setLeaveType] = useState('')
  const [page, setPage] = useState(1)
  const [deciding, setDeciding] = useState<{ lr: LeaveRequest; approve: boolean } | null>(null)
  const [comment, setComment] = useState('')
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['leave-requests', status, department, leaveType, page],
    queryFn: () => api.get<Page<LeaveRequest>>(`/leave/requests/${qs({ status, department, leave_type: leaveType, page })}`),
    placeholderData: (p) => p,
  })
  const decide = useMutation({
    mutationFn: ({ lr, approve }: { lr: LeaveRequest; approve: boolean }) => api.post(`/leave/requests/${lr.id}/${approve ? 'approve' : 'reject'}/`, { comment }),
    onSuccess: (_, v) => {
      setDeciding(null); setComment('')
      ;['leave-requests', 'hr-dashboard', 'attendance-board'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
      toast.success(`Leave ${v.approve ? 'approved' : 'rejected'}. ${v.lr.employee_name} has been notified.`)
    },
  })
  const canDecide = user.role === 'hr'
  return (
    <>
      <PageHeader title="Leave requests" subtitle={canDecide ? 'Approve or reject with a comment. Balances are re-checked at approval.' : 'All leave requests and decisions (view only).'} />
      <Tabs value={status} onChange={(v) => { setStatus(v); setPage(1) }}
        tabs={[{ id: 'pending', label: 'Pending' }, { id: 'approved', label: 'Approved' }, { id: 'rejected', label: 'Rejected' }, { id: '', label: 'All' }]} />
      <div className="mb-3 flex flex-wrap gap-2">
        <FilterSelect label="Department" value={department} onChange={(v) => { setDepartment(v); setPage(1) }}>
          <option value="">All departments</option>{depts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </FilterSelect>
        <FilterSelect label="Leave type" value={leaveType} onChange={(v) => { setLeaveType(v); setPage(1) }}>
          <option value="">All types</option>{types?.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
        </FilterSelect>
      </div>
      <Card>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(r) => r.id}
              empty={<EmptyState title={status === 'pending' ? 'No pending requests' : 'No leave requests found'} />}
              columns={[
                { key: 'e', header: 'Employee', cell: (r) => <div><p className="font-medium">{r.employee_name}</p><p className="text-xs text-muted">{r.employee_code} · {r.department}</p></div> },
                { key: 't', header: 'Type', cell: (r) => <div className="flex items-center gap-1.5">{r.leave_type_name}{r.source === 'ai' && <Badge tone="violet">AI</Badge>}</div> },
                { key: 'd', header: 'Dates', cell: (r) => <span className="whitespace-nowrap">{fmtDate(r.start_date)}{r.end_date !== r.start_date && ` – ${fmtDate(r.end_date)}`}</span> },
                { key: 'n', header: 'Days', cell: (r) => r.days },
                { key: 'r', header: 'Reason', cell: (r) => <p className="max-w-xs text-sm">{r.reason}</p> },
                { key: 's', header: 'Status', cell: (r) => <div><StatusBadge status={r.status} />{r.decided_by_name && <p className="mt-1 text-[11px] text-muted">{r.decided_by_name} · {fmtDateTime(r.decided_at)}</p>}</div> },
                ...(canDecide ? [{ key: 'a', header: '', className: 'text-right', cell: (r: LeaveRequest) => r.status === 'pending' && r.employee !== user.employee_id && (
                  <div className="flex justify-end gap-1">
                    <IconButton label={`Approve leave for ${r.employee_name}`} className="hover:text-teal" onClick={() => { decide.reset(); setDeciding({ lr: r, approve: true }) }}><Check className="size-4" /></IconButton>
                    <IconButton label={`Reject leave for ${r.employee_name}`} className="hover:text-red" onClick={() => { decide.reset(); setDeciding({ lr: r, approve: false }) }}><X className="size-4" /></IconButton>
                  </div>) }] : []),
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={deciding !== null} onClose={() => setDeciding(null)} title={deciding?.approve ? 'Approve leave' : 'Reject leave'}
        footer={<><Button variant="secondary" onClick={() => setDeciding(null)}>Cancel</Button>
          <Button variant={deciding?.approve ? 'success' : 'danger'} loading={decide.isPending} onClick={() => deciding && decide.mutate(deciding)}>{deciding?.approve ? 'Approve' : 'Reject'}</Button></>}>
        {deciding && (
          <div className="space-y-3 text-sm">
            <p><b>{deciding.lr.employee_name}</b> · {deciding.lr.leave_type_name} · {fmtDate(deciding.lr.start_date)} – {fmtDate(deciding.lr.end_date)} ({deciding.lr.days} days)</p>
            <p className="text-muted">“{deciding.lr.reason}”</p>
            <Textarea label={deciding.approve ? 'Comment (optional)' : 'Reason for rejection'} required={!deciding.approve} value={comment} onChange={(e) => setComment(e.target.value)}
              maxLength={500} error={fieldError(decide.error, 'comment')} />
            {decide.error && !fieldError(decide.error, 'comment') && <Alert>{(decide.error as Error).message}</Alert>}
          </div>
        )}
      </Modal>
    </>
  )
}
