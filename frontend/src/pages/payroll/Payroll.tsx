import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Lock, Play, Plus, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useToast } from '../../components/toast'
import {
  Alert, Button, Card, ConfirmDialog, EmptyState, ErrorState, Input, Kpi, Modal, PageHeader, Pagination, Select, Spinner,
  StatusBadge, Table,
} from '../../components/ui'
import { api, download, fieldError, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDate, fmtDateTime, fmtMoney, fmtMonth, today } from '../../lib/format'
import type { Employee, Page, PayrollRun, Payslip } from '../../lib/types'

interface Salary { id: number; employee: number; employee_name: string; employee_code: string; basic: string; hra: string; medical: string; gross: string; effective_from: string; created_at: string }

function useAllEmployees() {
  return useQuery({ queryKey: ['employees', 'all'], queryFn: () => api.get<Page<Employee>>('/employees/?page_size=200&status=') })
}

export function SalariesPage() {
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: emps } = useAllEmployees()
  const [employee, setEmployee] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ employee: '', basic: '', effective_from: today() })
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['salaries', employee, page],
    queryFn: () => api.get<Page<Salary>>(`/payroll/salaries/${qs({ employee, page })}`),
  })
  const save = useMutation({
    mutationFn: () => api.post('/payroll/salaries/', form),
    onSuccess: () => { setOpen(false); qc.invalidateQueries({ queryKey: ['salaries'] }); qc.invalidateQueries({ queryKey: ['employee-360'] }); toast.success('Salary structure saved.') },
  })
  const canEdit = user.role === 'hr'
  const basic = Number(form.basic) || 0
  return (
    <>
      <PageHeader title="Salary structures" subtitle="Gross = 1.5 × basic (HRA 40% + medical 10%). The structure effective at month end is used in payroll."
        actions={canEdit && <Button onClick={() => { save.reset(); setForm({ employee, basic: '', effective_from: today() }); setOpen(true) }}><Plus className="size-4" /> Set salary</Button>} />
      <Card>
        <div className="mb-3 max-w-xs">
          <Select label="Employee" value={employee} onChange={(e) => { setEmployee(e.target.value); setPage(1) }}>
            <option value="">All employees</option>
            {emps?.results.map((e) => <option key={e.id} value={e.id}>{e.employee_code} · {e.full_name}</option>)}
          </Select>
        </div>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(s) => s.id} empty={<EmptyState title="No salary structures yet" body="They are created when HR registers an employee." />}
              columns={[
                { key: 'e', header: 'Employee', cell: (s) => <Link className="hover:underline" to={`/employees/${s.employee}`}><p className="font-medium">{s.employee_name}</p><p className="text-xs text-muted">{s.employee_code}</p></Link> },
                { key: 'b', header: 'Basic', cell: (s) => <span className="tabular">{fmtMoney(s.basic)}</span> },
                { key: 'h', header: 'HRA', cell: (s) => <span className="tabular">{fmtMoney(s.hra)}</span> },
                { key: 'm', header: 'Medical', cell: (s) => <span className="tabular">{fmtMoney(s.medical)}</span> },
                { key: 'g', header: 'Gross', cell: (s) => <span className="tabular font-semibold">{fmtMoney(s.gross)}</span> },
                { key: 'f', header: 'Effective from', cell: (s) => fmtDate(s.effective_from) },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Set salary structure"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
          <Select label="Employee" required value={form.employee} onChange={(e) => setForm({ ...form, employee: e.target.value })} error={fieldError(save.error, 'employee')}>
            <option value="">Select…</option>
            {emps?.results.filter((e) => e.employment_status !== 'exited' && e.user_id !== user.id).map((e) => <option key={e.id} value={e.id}>{e.employee_code} · {e.full_name}</option>)}
          </Select>
          <div className="grid grid-cols-2 gap-3">
            <Input label="Basic (monthly)" type="number" min={1} step="0.01" required value={form.basic} onChange={(e) => setForm({ ...form, basic: e.target.value })} error={fieldError(save.error, 'basic')} />
            <Input label="Effective from" type="date" required value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} />
          </div>
          {basic > 0 && (
            <dl className="grid grid-cols-4 gap-2 rounded-lg bg-surface-2 p-3 text-xs">
              {[['Basic', basic], ['HRA 40%', basic * 0.4], ['Medical 10%', basic * 0.1], ['Gross', basic * 1.5]].map(([k, v]) => (
                <div key={k as string}><dt className="text-muted">{k}</dt><dd className="tabular mt-0.5 font-semibold">{fmtMoney(v as number)}</dd></div>
              ))}
            </dl>
          )}
          {save.error && !fieldError(save.error, 'basic') && !fieldError(save.error, 'employee') && <Alert>{(save.error as Error).message}</Alert>}
          <button type="submit" hidden />
        </form>
      </Modal>
    </>
  )
}

export function PayrollRunsPage() {
  const user = useUser()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const now = new Date()
  const [period, setPeriod] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['payroll-runs'], queryFn: () => api.get<Page<PayrollRun>>('/payroll/runs/') })
  const run = useMutation({
    mutationFn: () => { const [year, month] = period.split('-').map(Number); return api.post<PayrollRun>('/payroll/runs/', { year, month }) },
    onSuccess: (r) => { setOpen(false); navigate(`/payroll/${r.id}`) },
  })
  return (
    <>
      <PageHeader title="Payroll runs" subtitle={user.role === 'hr' ? 'Prepare the monthly draft; Admin reviews and finalizes it.' : 'Review drafts prepared by HR and finalize them.'}
        actions={user.role === 'hr' && <Button onClick={() => { run.reset(); setOpen(true) }}><Play className="size-4" /> Run payroll</Button>} />
      <Card>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <Table rows={data?.results ?? []} rowKey={(r) => r.id} onRowClick={(r) => navigate(`/payroll/${r.id}`)}
            empty={<EmptyState title="No payroll runs yet" body={user.role === 'hr' ? 'Run payroll for a month to create a draft.' : 'HR has not prepared a payroll draft yet.'} />}
            columns={[
              { key: 'p', header: 'Period', cell: (r) => <span className="font-medium">{fmtMonth(r.period)}</span> },
              { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
              { key: 'e', header: 'Employees', cell: (r) => r.employee_count },
              { key: 'g', header: 'Gross', cell: (r) => <span className="tabular">{fmtMoney(r.total_gross)}</span> },
              { key: 'n', header: 'Net', cell: (r) => <span className="tabular font-semibold">{fmtMoney(r.total_net)}</span> },
              { key: 'f', header: 'Finalized', cell: (r) => r.finalized_at ? `${r.finalized_by_name ?? ''} · ${fmtDateTime(r.finalized_at)}` : '—' },
            ]} />
        )}
      </Card>
      <Modal open={open} onClose={() => setOpen(false)} title="Run payroll"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button loading={run.isPending} onClick={() => run.mutate()}>Generate draft</Button></>}>
        <div className="space-y-3">
          <Input label="Month" type="month" value={period} max={`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`} onChange={(e) => setPeriod(e.target.value)} />
          <p className="text-sm text-muted">Uses each employee's salary structure, absences, unpaid leave and half days recorded so far. Running the current month counts days up to today; you can regenerate the draft later.</p>
          {run.error && <Alert>{(run.error as Error).message}</Alert>}
        </div>
      </Modal>
    </>
  )
}

export function PayrollRunDetailPage() {
  const { id } = useParams()
  const user = useUser()
  const qc = useQueryClient()
  const toast = useToast()
  const [confirm, setConfirm] = useState(false)
  const [slip, setSlip] = useState<Payslip | null>(null)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['payroll-run', id], queryFn: () => api.get<PayrollRun & { payslips: Payslip[] }>(`/payroll/runs/${id}/`) })
  const invalidate = () => ['payroll-run', 'payroll-runs', 'admin-dashboard'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
  const regen = useMutation({ mutationFn: () => api.post(`/payroll/runs/${id}/regenerate/`), onSuccess: () => { invalidate(); toast.success('Draft recalculated from current records.') }, onError: toast.error })
  const finalize = useMutation({
    mutationFn: () => api.post(`/payroll/runs/${id}/finalize/`),
    onSuccess: () => { setConfirm(false); invalidate(); toast.success('Payroll finalized and locked. Employees were notified.') },
    onError: (e) => { setConfirm(false); toast.error(e) },
  })
  if (error) return <ErrorState error={error} retry={refetch} />
  if (isLoading || !data) return <Spinner />
  const locked = data.status === 'finalized'
  return (
    <>
      <Link to="/payroll" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Payroll runs</Link>
      <PageHeader title={`Payroll · ${fmtMonth(data.period)}`}
        subtitle={<>{data.working_days} working days · generated {fmtDateTime(data.generated_at)} by {data.created_by_name ?? '—'}</>}
        actions={<>
          <StatusBadge status={data.status} />
          {user.role === 'hr' && !locked && <Button variant="secondary" loading={regen.isPending} onClick={() => regen.mutate()}><RefreshCw className="size-4" /> Recalculate</Button>}
          {user.role === 'admin' && !locked && <Button onClick={() => setConfirm(true)} disabled={!data.employee_count}><Lock className="size-4" /> Finalize</Button>}
        </>} />
      {locked
        ? <Alert tone="teal">Finalized by {data.finalized_by_name} on {fmtDateTime(data.finalized_at)}. This run is locked; payslips are snapshots and will not change.</Alert>
        : <Alert tone="amber">Draft. {user.role === 'admin' ? 'Review the figures, then finalize to lock the month and release payslips.' : 'Admin must finalize this run before employees can see their payslips.'}</Alert>}
      <div className="my-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Employees" value={data.employee_count} />
        <Kpi label="Earned gross" value={fmtMoney(data.total_gross)} tone="violet" />
        <Kpi label="Deductions + tax" value={fmtMoney(Number(data.total_deductions) + Number(data.total_tax))} tone="red" hint={`Tax ${fmtMoney(data.total_tax)}`} />
        <Kpi label="Net pay" value={fmtMoney(data.total_net)} tone="teal" />
      </div>
      <Card title="Payslips">
        <Table rows={data.payslips} rowKey={(p) => p.id} onRowClick={setSlip} empty={<EmptyState title="No employees with a salary in this month" />}
          columns={[
            { key: 'e', header: 'Employee', cell: (p) => <div><p className="font-medium">{p.employee_name}</p><p className="text-xs text-muted">{p.employee_code} · {p.department_name}</p></div> },
            { key: 'g', header: 'Gross', cell: (p) => <span className="tabular">{fmtMoney(p.gross)}</span> },
            { key: 'd', header: 'Payable days', cell: (p) => `${p.payable_days}/${p.working_days}` },
            { key: 'x', header: 'Absent / unpaid / half', cell: (p) => `${Number(p.absent_days)} / ${Number(p.unpaid_leave_days)} / ${Number(p.half_days)}` },
            { key: 'de', header: 'Deduction', cell: (p) => <span className="tabular">{fmtMoney(p.deduction)}</span> },
            { key: 't', header: 'Tax', cell: (p) => <span className="tabular">{fmtMoney(p.tax)}</span> },
            { key: 'n', header: 'Net', cell: (p) => <span className="tabular font-semibold">{fmtMoney(p.net)}</span> },
          ]} />
      </Card>
      <PayslipModal slip={slip} onClose={() => setSlip(null)} />
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} title={`Finalize ${fmtMonth(data.period)} payroll?`} confirmLabel="Finalize and lock"
        loading={finalize.isPending} onConfirm={() => finalize.mutate()}
        body={<>This locks {data.employee_count} payslips (net {fmtMoney(data.total_net)}). It cannot be undone or edited afterwards, and leave or attendance corrections for this month will be blocked. Employees are notified.</>} />
    </>
  )
}

export function PayslipModal({ slip, onClose }: { slip: Payslip | null; onClose: () => void }) {
  const toast = useToast()
  if (!slip) return null
  const rows: [string, string | number, boolean?][] = [
    ['Basic', fmtMoney(slip.basic)], ['HRA (40%)', fmtMoney(slip.hra)], ['Medical (10%)', fmtMoney(slip.medical)], ['Monthly gross', fmtMoney(slip.gross), true],
    [`Prorated gross (${slip.payable_days}/${slip.working_days} days)`, fmtMoney(slip.prorated_gross)],
    [`Deduction: ${Number(slip.absent_days)} absent + ${Number(slip.unpaid_leave_days)} unpaid + ${Number(slip.half_days)} × 0.5 half${Number(slip.late_penalty_days) ? ` + ${Number(slip.late_penalty_days)} late penalty` : ''} @ ${fmtMoney(slip.per_day_rate)}/day`, `− ${fmtMoney(slip.deduction)}`],
    ['Earned gross', fmtMoney(slip.earned_gross), true],
    [`Income tax (annual ${fmtMoney(slip.annual_tax)} on ${fmtMoney(slip.annual_taxable)})`, `− ${fmtMoney(slip.tax)}`],
  ]
  return (
    <Modal open onClose={onClose} title={`${slip.employee_name} · ${fmtMonth(slip.period)}`}
      footer={<Button variant="secondary" onClick={() => download(`/payroll/payslips/${slip.id}/pdf/`, `payslip-${slip.period}.pdf`).catch(toast.error)}><Download className="size-4" /> Download PDF</Button>}>
      <dl className="space-y-2 text-sm">
        {rows.map(([k, v, bold]) => (
          <div key={k} className={`flex justify-between gap-4 ${bold ? 'border-t border-line pt-2 font-semibold' : ''}`}><dt className={bold ? '' : 'text-muted'}>{k}</dt><dd className="tabular shrink-0">{v}</dd></div>
        ))}
        <div className="flex justify-between rounded-lg bg-teal-soft px-3 py-2 text-base font-semibold text-teal"><dt>Net pay</dt><dd className="tabular">{fmtMoney(slip.net)}</dd></div>
      </dl>
      <p className="mt-3 text-xs text-muted">Tax slabs are illustrative (challenge brief), not current tax law.</p>
    </Modal>
  )
}

export function PayslipsPage() {
  const user = useUser()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [slip, setSlip] = useState<Payslip | null>(null)
  const mineOnly = user.role === 'employee'
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['payslips', page],
    queryFn: () => api.get<Page<Payslip>>(`/payroll/payslips/${qs({ page })}`),
  })
  return (
    <>
      <PageHeader title={mineOnly ? 'My payslips' : 'Payslips'} subtitle={mineOnly ? 'Payslips appear here once Admin finalizes the month.' : 'All payslips across payroll runs.'} />
      <Card>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(p) => p.id} onRowClick={setSlip}
              empty={<EmptyState title="No payslips yet" body={mineOnly ? 'You will be notified when your first payslip is ready.' : undefined} />}
              columns={[
                { key: 'p', header: 'Period', cell: (p) => <span className="font-medium">{fmtMonth(p.period)}</span> },
                ...(!mineOnly ? [{ key: 'e', header: 'Employee', cell: (p: Payslip) => `${p.employee_code} · ${p.employee_name}` }] : []),
                { key: 'g', header: 'Earned gross', cell: (p) => <span className="tabular">{fmtMoney(p.earned_gross)}</span> },
                { key: 't', header: 'Tax', cell: (p) => <span className="tabular">{fmtMoney(p.tax)}</span> },
                { key: 'n', header: 'Net', cell: (p) => <span className="tabular font-semibold">{fmtMoney(p.net)}</span> },
                { key: 's', header: 'Status', cell: (p) => <StatusBadge status={p.run_status} /> },
                { key: 'a', header: '', className: 'text-right', cell: (p) => (
                  <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); download(`/payroll/payslips/${p.id}/pdf/`, `payslip-${p.period}.pdf`).catch(toast.error) }}>
                    <Download className="size-4" /> PDF</Button>) },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <PayslipModal slip={slip} onClose={() => setSlip(null)} />
    </>
  )
}
