import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Pencil, Plus, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useToast } from '../../components/toast'
import {
  Alert, Button, Card, EmptyState, ErrorState, FilterSelect, Input, Kpi, Modal, PageHeader, Pagination, Select, Spinner,
  StatusBadge, Table,
} from '../../components/ui'
import { api, download, fieldError, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDate, fmtMoney, fmtPct, fmtTime, label, today } from '../../lib/format'
import { useDepartments, useDesignations } from '../../lib/queries'
import type { AttendanceSummary, Balance, Employee, Page } from '../../lib/types'
import { TempPasswordNotice } from '../admin/Users'

export function EmployeesPage() {
  const user = useUser()
  const navigate = useNavigate()
  const isHR = user.role === 'hr'
  const { data: depts } = useDepartments()
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [formOpen, setFormOpen] = useState(false)
  useEffect(() => { const t = setTimeout(() => { setDebounced(search); setPage(1) }, 300); return () => clearTimeout(t) }, [search])
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['employees', debounced, department, status, page],
    queryFn: () => api.get<Page<Employee>>(`/employees/${qs({ search: debounced, department, status, page })}`),
    placeholderData: (p) => p,
  })
  const toast = useToast()
  return (
    <>
      <PageHeader title="Employees" subtitle={isHR ? 'Register employees, keep records current and import or export in bulk.' : 'Company-wide employee directory.'}
        actions={isHR && <>
          <Button variant="secondary" onClick={() => download(`/employees/export/${qs({ search: debounced, department, status })}`, 'employees.csv').catch(toast.error)}><Download className="size-4" /> Export CSV</Button>
          <Link to="/employees/import"><Button variant="secondary"><Upload className="size-4" /> Import CSV</Button></Link>
          <Button onClick={() => setFormOpen(true)}><Plus className="size-4" /> Register employee</Button>
        </>} />
      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          <input aria-label="Search employees" placeholder="Search name, code, email or phone" value={search} onChange={(e) => setSearch(e.target.value)}
            className="h-9 w-full max-w-sm rounded-lg border border-line bg-surface px-3 text-sm focus:border-teal focus:outline-none" />
          <FilterSelect label="Department" value={department} onChange={(v) => { setDepartment(v); setPage(1) }}>
            <option value="">All departments</option>
            {depts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </FilterSelect>
          <FilterSelect label="Status" value={status} onChange={(v) => { setStatus(v); setPage(1) }}>
            <option value="">Any status</option><option value="active">Active</option><option value="probation">Probation</option><option value="exited">Exited</option>
          </FilterSelect>
          {isFetching && !isLoading && <span className="self-center text-xs text-muted">Updating…</span>}
        </div>
        {error ? <ErrorState error={error} retry={refetch} /> : isLoading ? <Spinner /> : (
          <>
            <Table rows={data?.results ?? []} rowKey={(e) => e.id} onRowClick={(e) => navigate(`/employees/${e.id}`)}
              empty={<EmptyState title={debounced || department || status ? 'No employees match these filters' : 'No employees yet'}
                body={isHR && !debounced ? 'Register the first employee; their login is created automatically.' : undefined}
                action={isHR && !debounced && <Button onClick={() => setFormOpen(true)}><Plus className="size-4" /> Register employee</Button>} />}
              columns={[
                { key: 'n', header: 'Employee', cell: (e) => <div><p className="font-medium">{e.full_name}</p><p className="text-xs text-muted">{e.employee_code} · {e.email}</p></div> },
                { key: 'd', header: 'Department', cell: (e) => e.department_name },
                { key: 'g', header: 'Designation', cell: (e) => e.designation_name ?? '—' },
                { key: 'j', header: 'Joined', cell: (e) => fmtDate(e.join_date) },
                { key: 's', header: 'Status', cell: (e) => <StatusBadge status={e.employment_status} /> },
              ]} />
            <Pagination page={page} count={data?.count ?? 0} onPage={setPage} />
          </>
        )}
      </Card>
      <EmployeeForm open={formOpen} onClose={() => setFormOpen(false)} />
    </>
  )
}

type FormState = {
  employee_code: string; first_name: string; last_name: string; email: string; phone: string; address: string; gender: string
  date_of_birth: string; department: string; designation: string; join_date: string; exit_date: string; employment_status: string; basic_salary: string
}

const emptyForm = (): FormState => ({ employee_code: '', first_name: '', last_name: '', email: '', phone: '', address: '', gender: 'unspecified',
  date_of_birth: '', department: '', designation: '', join_date: today(), exit_date: '', employment_status: 'probation', basic_salary: '' })

export function EmployeeForm({ open, onClose, employee }: { open: boolean; onClose: () => void; employee?: Employee }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: depts } = useDepartments()
  const { data: desigs } = useDesignations()
  const [form, setForm] = useState<FormState>(emptyForm)
  const [issued, setIssued] = useState<{ email: string; password: string } | null>(null)
  useEffect(() => {
    if (!open) return
    setForm(employee ? {
      ...emptyForm(), ...Object.fromEntries(Object.entries(employee).map(([k, v]) => [k, v === null ? '' : String(v)])),
    } as FormState : emptyForm())
  }, [open, employee])
  const save = useMutation({
    mutationFn: (): Promise<unknown> => {
      const body: Record<string, unknown> = { ...form, designation: form.designation || null, date_of_birth: form.date_of_birth || null, exit_date: form.exit_date || null }
      if (employee) { delete body.basic_salary; return api.patch<Employee>(`/employees/${employee.id}/`, body) }
      return api.post<{ employee: Employee; temporary_password: string | null }>('/employees/', body)
    },
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['employees'] })
      qc.invalidateQueries({ queryKey: ['employee-360'] })
      onClose()
      if (!employee) {
        const res = r as { employee: Employee; temporary_password: string | null }
        if (res.temporary_password) setIssued({ email: res.employee.email, password: res.temporary_password })
        else toast.success(`${res.employee.full_name} registered and linked to the existing HR login.`)
      } else toast.success('Employee updated.')
    },
  })
  const set = (k: keyof FormState) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const err = save.error
  const fe = (k: string) => fieldError(err, k)
  const anyField = Object.keys(form).some((k) => fe(k))
  return (
    <>
      <Modal open={open} onClose={onClose} wide title={employee ? `Edit ${employee.full_name}` : 'Register employee'}
        footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={save.isPending} onClick={() => save.mutate()}>{employee ? 'Save changes' : 'Register & create login'}</Button></>}>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate() }}>
          <Input label="Employee code" required value={form.employee_code} onChange={set('employee_code')} error={fe('employee_code')} placeholder="E001" />
          <Input label="Work email (login)" type="email" required value={form.email} onChange={set('email')} error={fe('email')} />
          <Input label="First name" required value={form.first_name} onChange={set('first_name')} error={fe('first_name')} />
          <Input label="Last name" value={form.last_name} onChange={set('last_name')} />
          <Select label="Department" required value={form.department} onChange={set('department')} error={fe('department')}>
            <option value="">Select…</option>
            {depts?.filter((d) => d.is_active).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
          <Select label="Designation" value={form.designation} onChange={set('designation')}>
            <option value="">—</option>
            {desigs?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
          <Input label="Join date" type="date" required value={form.join_date} onChange={set('join_date')} error={fe('join_date')} />
          <Select label="Employment status" value={form.employment_status} onChange={set('employment_status')} error={fe('employment_status')}>
            <option value="probation">Probation</option><option value="active">Active</option>{employee && <option value="exited">Exited</option>}
          </Select>
          {employee && form.employment_status === 'exited' && (
            <Input label="Exit date" type="date" required value={form.exit_date} onChange={set('exit_date')} error={fe('exit_date')} hint="Exiting deactivates the login." />
          )}
          {!employee && (
            <Input label="Basic salary (monthly)" type="number" min={1} step="0.01" required value={form.basic_salary} onChange={set('basic_salary')}
              error={fe('basic_salary')} hint={form.basic_salary ? `Gross = 1.5 × basic = ${fmtMoney(Number(form.basic_salary) * 1.5)}` : 'Gross = 1.5 × basic (HRA 40%, medical 10%)'} />
          )}
          <Select label="Gender" value={form.gender} onChange={set('gender')}>
            <option value="unspecified">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option>
          </Select>
          <Input label="Date of birth" type="date" value={form.date_of_birth} onChange={set('date_of_birth')} />
          <Input label="Phone" value={form.phone} onChange={set('phone')} />
          <div className="sm:col-span-2"><Input label="Address" value={form.address} onChange={set('address')} /></div>
          {err && !anyField && <div className="sm:col-span-2"><Alert>{(err as Error).message}</Alert></div>}
          <button type="submit" hidden />
        </form>
      </Modal>
      <Modal open={issued !== null} onClose={() => setIssued(null)} title="Employee registered" footer={<Button onClick={() => setIssued(null)}>Done</Button>}>
        {issued && <TempPasswordNotice email={issued.email} password={issued.password} />}
      </Modal>
    </>
  )
}

interface Profile360 {
  employee: Employee
  attendance_30d: AttendanceSummary
  recent_attendance: { date: string; status: string; check_in: string; check_out: string | null; worked_minutes: number | null; source: string }[]
  leave_balance: { year: number; balances: Balance[] }
  recent_leaves: { id: number; type: string; start_date: string; end_date: string; days: number; status: string }[]
  payslips: { id: number; period: string; status: string; net: string }[]
  salary?: { basic: string; hra: string; medical: string; gross: string; effective_from: string } | null
}

export function Employee360Page() {
  const { id } = useParams()
  const user = useUser()
  const [editing, setEditing] = useState(false)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['employee-360', id], queryFn: () => api.get<Profile360>(`/employees/${id}/360/`) })
  if (error) return <ErrorState error={error} retry={refetch} />
  if (isLoading || !data) return <Spinner />
  const e = data.employee
  return (
    <>
      <Link to={user.role === 'employee' ? '/profile' : '/employees'} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Back</Link>
      <PageHeader title={e.full_name} subtitle={<>{e.employee_code} · {e.designation_name ?? 'No designation'} · {e.department_name}</>}
        actions={<>
          <StatusBadge status={e.employment_status} />
          {!e.is_login_active && <StatusBadge status="inactive" text="Login disabled" />}
          {user.role === 'hr' && <Button variant="secondary" onClick={() => setEditing(true)}><Pencil className="size-4" /> Edit</Button>}
        </>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Profile">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {[['Email', e.email], ['Phone', e.phone || '—'], ['Joined', fmtDate(e.join_date)], ['Exit', fmtDate(e.exit_date)],
              ['Gender', label(e.gender)], ['Date of birth', fmtDate(e.date_of_birth)]].map(([k, v]) => (
              <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 break-words">{v}</dd></div>
            ))}
            <div className="col-span-2"><dt className="text-xs text-muted">Address</dt><dd className="mt-0.5">{e.address || '—'}</dd></div>
          </dl>
        </Card>
        <Card title="Last 30 days">
          <div className="grid grid-cols-2 gap-3">
            <Kpi label="Attendance rate" value={fmtPct(data.attendance_30d.attendance_rate)} />
            <Kpi label="Late arrivals" value={data.attendance_30d.late_arrivals} tone="amber" />
            <Kpi label="Absent days" value={data.attendance_30d.absent} tone="red" />
            <Kpi label="On leave" value={data.attendance_30d.on_leave} tone="blue" />
          </div>
        </Card>
        <Card title={data.salary ? 'Salary structure' : 'Leave balance'}>
          {data.salary ? (
            <dl className="space-y-2 text-sm">
              {[['Basic', data.salary.basic], ['HRA (40%)', data.salary.hra], ['Medical (10%)', data.salary.medical]].map(([k, v]) => (
                <div key={k} className="flex justify-between"><dt className="text-muted">{k}</dt><dd className="tabular">{fmtMoney(v)}</dd></div>
              ))}
              <div className="flex justify-between border-t border-line pt-2 font-semibold"><dt>Gross</dt><dd className="tabular">{fmtMoney(data.salary.gross)}</dd></div>
              <p className="text-xs text-muted">Effective from {fmtDate(data.salary.effective_from)}</p>
            </dl>
          ) : <p className="text-sm text-muted">No salary data.</p>}
        </Card>
        <Card title={`Leave balance ${data.leave_balance.year}`}>
          <ul className="space-y-2 text-sm">
            {data.leave_balance.balances.map((b) => (
              <li key={b.code} className="flex justify-between"><span>{b.name}</span>
                <span className="tabular text-muted">{b.quota === null ? `${b.used} used` : `${b.remaining}/${b.quota} left`}{b.pending ? ` · ${b.pending} pending` : ''}</span></li>
            ))}
          </ul>
        </Card>
        <Card title="Recent attendance" className="lg:col-span-2">
          <Table rows={data.recent_attendance} rowKey={(r) => r.date} empty={<EmptyState title="No attendance yet" />}
            columns={[
              { key: 'd', header: 'Date', cell: (r) => fmtDate(r.date) },
              { key: 'i', header: 'In', cell: (r) => fmtTime(r.check_in) },
              { key: 'o', header: 'Out', cell: (r) => fmtTime(r.check_out) },
              { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
              { key: 'src', header: 'Source', cell: (r) => label(r.source) },
            ]} />
        </Card>
        <Card title="Recent leave" className="lg:col-span-2">
          <Table rows={data.recent_leaves} rowKey={(r) => r.id} empty={<EmptyState title="No leave requests" />}
            columns={[
              { key: 't', header: 'Type', cell: (r) => r.type },
              { key: 'd', header: 'Dates', cell: (r) => `${fmtDate(r.start_date)} – ${fmtDate(r.end_date)}` },
              { key: 'n', header: 'Days', cell: (r) => r.days },
              { key: 's', header: 'Status', cell: (r) => <StatusBadge status={r.status} /> },
            ]} />
        </Card>
        <Card title="Payslips">
          <Table rows={data.payslips} rowKey={(r) => r.id} empty={<EmptyState title="No payslips yet" />}
            columns={[
              { key: 'p', header: 'Period', cell: (r) => r.period },
              { key: 'n', header: 'Net', cell: (r) => fmtMoney(r.net) },
              { key: 's', header: '', cell: (r) => <StatusBadge status={r.status} /> },
            ]} />
        </Card>
      </div>
      {user.role === 'hr' && <EmployeeForm open={editing} onClose={() => { setEditing(false); refetch() }} employee={e} />}
    </>
  )
}

interface DryRun { dry_run: true; total_rows: number; valid_rows: number; errors: { row: number; field: string; reason: string }[] }

export function CsvImportPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<DryRun | null>(null)
  const [created, setCreated] = useState<{ employee_code: string; email: string; temporary_password: string }[] | null>(null)
  const send = useMutation({
    mutationFn: (dry: boolean) => {
      const form = new FormData()
      form.append('file', file as File)
      form.append('dry_run', String(dry))
      return api.upload<DryRun | { created: { employee_code: string; email: string; temporary_password: string }[] }>('/employees/import/', form)
    },
    onSuccess: (r) => {
      if ('created' in r) { setCreated(r.created); setReport(null); qc.invalidateQueries({ queryKey: ['employees'] }); toast.success(`Imported ${r.created.length} employees.`) }
      else setReport(r)
    },
  })
  return (
    <>
      <Link to="/employees" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Employees</Link>
      <PageHeader title="Import employees from CSV" subtitle="Run a dry run first: nothing is saved until every row is valid."
        actions={<Button variant="secondary" onClick={() => download('/employees/csv-template/', 'employee-import-template.csv').catch(toast.error)}><Download className="size-4" /> Template</Button>} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="1. Choose file" className="lg:col-span-1">
          <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setReport(null); setCreated(null); send.reset() }}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-teal-soft file:px-3 file:py-2 file:text-sm file:font-medium file:text-teal" />
          <p className="mt-3 text-xs text-muted">Required columns: employee_code, first_name, email, department (name or code), join_date (YYYY-MM-DD), basic_salary. Optional: last_name, phone, designation, gender, employment_status, address. Max 1000 rows.</p>
          <div className="mt-4 flex gap-2">
            <Button variant="secondary" disabled={!file} loading={send.isPending && send.variables === true} onClick={() => send.mutate(true)}>Dry run</Button>
            <Button disabled={!file || !report || report.errors.length > 0} loading={send.isPending && send.variables === false} onClick={() => send.mutate(false)}>Import</Button>
          </div>
        </Card>
        <Card title="2. Validation report" className="lg:col-span-2">
          {send.error && <Alert>{(send.error as Error).message}</Alert>}
          {!report && !created && !send.error && <p className="text-sm text-muted">Run a dry run to see row-by-row errors.</p>}
          {report && (
            <>
              <div className="mb-3 flex flex-wrap gap-3 text-sm">
                <span>{report.total_rows} rows</span><span className="text-teal">{report.valid_rows} valid</span>
                <span className={report.errors.length ? 'text-red' : 'text-muted'}>{report.errors.length} errors</span>
              </div>
              {report.errors.length === 0 ? <Alert tone="teal">All rows are valid. Click Import to create the employees and their logins.</Alert> : (
                <Table rows={report.errors} rowKey={(r) => `${r.row}-${r.field}-${r.reason}`}
                  columns={[{ key: 'r', header: 'Row', cell: (r) => r.row }, { key: 'f', header: 'Field', cell: (r) => <code className="text-xs">{r.field}</code> },
                    { key: 'x', header: 'Reason', cell: (r) => r.reason }]} />
              )}
            </>
          )}
          {created && (
            <>
              <Alert tone="teal">Imported {created.length} employees. Share each temporary password securely; it is shown only now.</Alert>
              <div className="mt-3"><Table rows={created} rowKey={(r) => r.email}
                columns={[{ key: 'c', header: 'Code', cell: (r) => r.employee_code }, { key: 'e', header: 'Email', cell: (r) => r.email },
                  { key: 'p', header: 'Temporary password', cell: (r) => r.temporary_password ? <code className="select-all">{r.temporary_password}</code> : 'Linked to HR login' }]} /></div>
            </>
          )}
        </Card>
      </div>
    </>
  )
}
