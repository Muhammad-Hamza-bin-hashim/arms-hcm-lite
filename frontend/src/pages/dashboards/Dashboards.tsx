import { useQuery } from '@tanstack/react-query'
import {
  AlarmClock, Banknote, CalendarClock, CalendarDays, ClipboardList, Clock, FileText, TrendingDown, UserCheck, Users, Wallet,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BarSeries, DataTable, TrendLine } from '../../components/charts'
import { CheckInWidget } from '../../components/CheckInWidget'
import { AISummary, AnnouncementsCard, defaultFilters, FilterBar, InsightsCard, type Filters, type Insights } from '../../components/DashboardBits'
import {
  Alert, Button, Card, EmptyState, ErrorState, Kpi, PageHeader, Skeleton, Table,
} from '../../components/ui'
import { api, qs } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { fmtDateTime, fmtMoney, fmtPct, fmtShort, label } from '../../lib/format'
import type { AttendanceSummary, Balance } from '../../lib/types'

function KpiSkeletons({ n = 4 }: { n?: number }) {
  return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{Array.from({ length: n }, (_, i) => <Skeleton key={i} className="h-24" />)}</div>
}

/* ---------------- HR ---------------- */

interface HRData {
  filters: { from: string; to: string; department: string | null }
  today: { headcount: number; present: number; late: number; on_leave: number; not_checked_in: number; pending_approvals: number;
    pending_leave: number; pending_corrections: number; on_leave_list: { employee_id: number; name: string; code: string; department: string; leave_type: string; end_date: string }[] }
  headcount: number
  attendance: AttendanceSummary
  attendance_trend: { date: string; attendance_rate: number | null; present: number; late: number; absent: number; on_leave: number }[]
  absenteeism_by_department: { department: string; absenteeism_pct: number | null; absent: number; late_pct: number | null; attendance_rate: number | null }[]
  leave: { by_type: { code: string; name: string; approved_days: number; pending_requests: number; utilization_pct: number | null }[]; total_approved_days: number }
  top_late_comers: { employee_id: number; code: string; name: string; department: string; late_count: number }[]
  insights: Insights
}

export function HRDashboard() {
  const user = useUser()
  const [filters, setFilters] = useState<Filters>(defaultFilters)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['hr-dashboard', filters],
    queryFn: () => api.get<HRData>(`/dashboard/hr/${qs(filters)}`),
    placeholderData: (prev) => prev,
  })
  return (
    <>
      <PageHeader title="HR dashboard" subtitle="Live numbers from attendance, leave and employee records." />
      {user.employee_id && <div className="mb-5"><CheckInWidget /></div>}
      <FilterBar value={filters} onChange={setFilters} />
      {error && <ErrorState error={error} retry={refetch} />}
      {isLoading && <KpiSkeletons n={5} />}
      {data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <Kpi label="Headcount" value={data.headcount} icon={<Users className="size-4" />} hint="Active + probation" />
            <Kpi label="Present today" value={data.today.present} icon={<UserCheck className="size-4" />} hint={`${data.today.not_checked_in} not checked in yet`} />
            <Kpi label="On leave today" value={data.today.on_leave} icon={<CalendarDays className="size-4" />} tone="blue" />
            <Kpi label="Late today" value={data.today.late} icon={<AlarmClock className="size-4" />} tone="amber" />
            <Link to="/leave/requests?status=pending" className="block">
              <Kpi label="Pending approvals" value={data.today.pending_approvals} icon={<ClipboardList className="size-4" />} tone="violet"
                hint={`${data.today.pending_leave} leave · ${data.today.pending_corrections} corrections`} />
            </Link>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Attendance rate" value={fmtPct(data.attendance.attendance_rate)} hint={`${fmtShort(data.filters.from)} – ${fmtShort(data.filters.to)}`} />
            <Kpi label="Late %" value={fmtPct(data.attendance.late_pct)} hint="late ÷ (present + late)" tone="amber" />
            <Kpi label="Absenteeism" value={fmtPct(data.attendance.absenteeism_pct)} hint={`${data.attendance.absent} absent days`} tone="red" />
            <Kpi label="Approved leave days" value={data.leave.total_approved_days} hint="in range" tone="blue" />
          </div>

          <div className="grid gap-5 lg:grid-cols-5">
            <Card title="Attendance rate by day" className="lg:col-span-3">
              <TrendLine data={data.attendance_trend.map((d) => ({ ...d, day: fmtShort(d.date) }))} x="day" y="attendance_rate"
                name="Attendance rate" domain={[0, 100]} format={(v) => `${v}%`} />
              <DataTable rows={data.attendance_trend} columns={[{ key: 'date', label: 'Date' }, { key: 'attendance_rate', label: 'Rate %' },
                { key: 'present', label: 'Present' }, { key: 'late', label: 'Late' }, { key: 'absent', label: 'Absent' }, { key: 'on_leave', label: 'On leave' }]} />
            </Card>
            <div className="lg:col-span-2"><AISummary filters={filters} board="hr" /></div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Absenteeism by department (%)">
              <BarSeries horizontal data={data.absenteeism_by_department.map((d) => ({ ...d, absenteeism_pct: d.absenteeism_pct ?? 0 }))}
                x="department" y="absenteeism_pct" name="Absenteeism" format={(v) => `${v}%`} />
              <DataTable rows={data.absenteeism_by_department} columns={[{ key: 'department', label: 'Department' },
                { key: 'absenteeism_pct', label: 'Absent %' }, { key: 'late_pct', label: 'Late %' }, { key: 'attendance_rate', label: 'Attendance %' }]} />
            </Card>
            <Card title="Approved leave days by type">
              <BarSeries data={data.leave.by_type} x="name" y="approved_days" name="Approved days" />
              <DataTable rows={data.leave.by_type} columns={[{ key: 'name', label: 'Type' }, { key: 'approved_days', label: 'Days' },
                { key: 'pending_requests', label: 'Pending' }, { key: 'utilization_pct', label: 'Year utilization %' }]} />
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Top 5 late-comers">
              <Table rows={data.top_late_comers} rowKey={(r) => r.employee_id}
                empty={<EmptyState title="No late arrivals in this range" />}
                columns={[
                  { key: 'n', header: 'Employee', cell: (r) => <Link className="font-medium hover:underline" to={`/employees/${r.employee_id}`}>{r.name}</Link> },
                  { key: 'd', header: 'Department', cell: (r) => r.department },
                  { key: 'c', header: 'Late arrivals', cell: (r) => <span className="tabular font-semibold">{r.late_count}</span>, className: 'text-right' },
                ]} />
            </Card>
            <Card title="On leave today">
              <Table rows={data.today.on_leave_list} rowKey={(r) => r.employee_id} empty={<EmptyState title="Nobody is on leave today" />}
                columns={[
                  { key: 'n', header: 'Employee', cell: (r) => r.name },
                  { key: 't', header: 'Type', cell: (r) => r.leave_type },
                  { key: 'e', header: 'Until', cell: (r) => fmtShort(r.end_date) },
                ]} />
            </Card>
          </div>
          <InsightsCard insights={data.insights} />
          <AnnouncementsCard />
        </div>
      )}
    </>
  )
}

/* ---------------- Admin ---------------- */

interface AdminData {
  filters: { from: string; to: string }
  headcount: number
  headcount_by_status: Record<string, number>
  attrition_period: { exits: number; attrition_pct: number | null }
  attrition_ytd: { exits: number; attrition_pct: number | null }
  payroll: { total_gross: string; total_net: string; total_tax: string; payslip_count: number; by_department: { department: string; gross: string; net: string }[];
    by_month: { period: string; gross: string; net: string }[]; latest_runs: { period: string; status: string; total_net: string }[] }
  salary: { average_gross: string | null; by_department: { department: string; average_gross: string | null; count: number }[]; by_designation: { designation: string; average_gross: string | null; count: number }[] }
  headcount_by_department: { department: string; count: number }[]
  gender: { gender: string; count: number }[]
  tenure: { bucket: string; count: number }[]
  attendance: AttendanceSummary
  today: { present: number; on_leave: number; late: number; pending_approvals: number }
  audit_feed: { id: number; summary: string; actor: string; created_at: string }[]
  insights: Insights
}

export function AdminDashboard() {
  const [filters, setFilters] = useState<Filters>(defaultFilters)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['admin-dashboard', filters],
    queryFn: () => api.get<AdminData>(`/dashboard/admin/${qs(filters)}`),
    placeholderData: (prev) => prev,
  })
  return (
    <>
      <PageHeader title="Company dashboard" subtitle="Headcount, attrition and payroll across AR&MS." />
      <FilterBar value={filters} onChange={setFilters} />
      {error && <ErrorState error={error} retry={refetch} />}
      {isLoading && <KpiSkeletons />}
      {data && data.headcount === 0 && (
        <Alert tone="blue">No employees yet. Set up departments in <Link className="underline" to="/settings">Organization</Link>, create an HR login in <Link className="underline" to="/users">Users</Link>, then HR registers employees.</Alert>
      )}
      {data && (
        <div className="mt-5 space-y-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Headcount" value={data.headcount} icon={<Users className="size-4" />}
              hint={`${data.headcount_by_status.active ?? 0} active · ${data.headcount_by_status.probation ?? 0} probation`} />
            <Kpi label="Attrition YTD" value={fmtPct(data.attrition_ytd.attrition_pct)} icon={<TrendingDown className="size-4" />} tone="red"
              hint={`${data.attrition_ytd.exits} exits this year`} />
            <Kpi label="Payroll cost (finalized)" value={fmtMoney(data.payroll.total_gross)} icon={<Banknote className="size-4" />} tone="violet"
              hint={`Net ${fmtMoney(data.payroll.total_net)} · ${data.payroll.payslip_count} payslips`} />
            <Kpi label="Average gross salary" value={fmtMoney(data.salary.average_gross)} icon={<Wallet className="size-4" />} tone="blue" hint="Current salary structures" />
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Present today" value={data.today.present} />
            <Kpi label="On leave today" value={data.today.on_leave} tone="blue" />
            <Kpi label="Attendance rate" value={fmtPct(data.attendance.attendance_rate)} hint="selected range" />
            <Kpi label="Pending approvals" value={data.today.pending_approvals} tone="violet" />
          </div>

          <div className="grid gap-5 lg:grid-cols-5">
            <Card title="Headcount by department" className="lg:col-span-3">
              <BarSeries horizontal data={data.headcount_by_department} x="department" y="count" name="Employees" />
              <DataTable rows={data.headcount_by_department} columns={[{ key: 'department', label: 'Department' }, { key: 'count', label: 'Employees' }]} />
            </Card>
            <div className="lg:col-span-2"><AISummary filters={filters} board="admin" /></div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Payroll cost by department (finalized, gross)">
              <BarSeries horizontal data={data.payroll.by_department.map((d) => ({ ...d, gross: Number(d.gross) }))} x="department" y="gross" name="Gross" />
              <DataTable rows={data.payroll.by_department} columns={[{ key: 'department', label: 'Department' },
                { key: 'gross', label: 'Gross', format: (v: string) => fmtMoney(v) }, { key: 'net', label: 'Net', format: (v: string) => fmtMoney(v) }]} />
            </Card>
            <Card title="Average gross salary by department">
              <BarSeries horizontal data={data.salary.by_department.map((d) => ({ ...d, average_gross: Number(d.average_gross ?? 0) }))}
                x="department" y="average_gross" name="Average gross" />
              <DataTable rows={data.salary.by_designation} columns={[{ key: 'designation', label: 'Designation' },
                { key: 'average_gross', label: 'Average gross', format: (v: string) => fmtMoney(v) }, { key: 'count', label: 'Employees' }]} />
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <Card title="Gender">
              <BarSeries data={data.gender.map((g) => ({ ...g, gender: label(g.gender) }))} x="gender" y="count" name="Employees" height={200} />
            </Card>
            <Card title="Tenure">
              <BarSeries data={data.tenure} x="bucket" y="count" name="Employees" height={200} />
            </Card>
            <Card title="Recent activity" action={<Link to="/audit" className="text-xs text-teal hover:underline">Audit log</Link>}>
              {!data.audit_feed.length && <EmptyState title="No activity yet" />}
              <ul className="space-y-2.5">
                {data.audit_feed.map((a) => (
                  <li key={a.id} className="text-sm">
                    <p className="line-clamp-1">{a.summary}</p>
                    <p className="text-[11px] text-muted">{a.actor || 'system'} · {fmtDateTime(a.created_at)}</p>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
          <InsightsCard insights={data.insights} />
          <AnnouncementsCard />
        </div>
      )}
    </>
  )
}

/* ---------------- Employee ---------------- */

interface EmployeeData {
  has_profile: boolean
  employee: { name: string; code: string; department: string }
  hours_this_week: number
  target_hours: number
  late_count_month: number
  month_attendance: AttendanceSummary
  leave_balance: { year: number; balances: Balance[] }
  last_payslip: { id: number; period: string; net: string } | null
}

export function EmployeeDashboard() {
  const user = useUser()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['employee-dashboard'], queryFn: () => api.get<EmployeeData>('/dashboard/employee/') })
  if (error) return <ErrorState error={error} retry={refetch} />
  if (isLoading || !data) return <><PageHeader title={`Hello, ${user.first_name || user.full_name}`} /><KpiSkeletons /></>
  if (!data.has_profile) return <EmptyState title="No employee profile" body="Your login is not linked to an employee record. Contact HR." />
  const pct = Math.min(100, Math.round((data.hours_this_week / data.target_hours) * 100))
  return (
    <>
      <PageHeader title={`Hello, ${user.first_name || user.full_name}`} subtitle={`${data.employee.code} · ${data.employee.department}`} />
      <div className="space-y-5">
        <CheckInWidget />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="flex items-center justify-between text-xs font-medium text-muted">Hours this week <Clock className="size-4 text-teal" /></p>
            <p className="tabular mt-2 text-2xl font-semibold">{data.hours_this_week}<span className="text-sm font-normal text-muted"> / {data.target_hours} h</span></p>
            <div className="mt-2 h-1.5 rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Weekly hours">
              <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <Kpi label="Late this month" value={data.late_count_month} tone="amber" icon={<AlarmClock className="size-4" />} />
          <Kpi label="Attendance rate (month)" value={fmtPct(data.month_attendance.attendance_rate)} icon={<CalendarClock className="size-4" />}
            hint={`${data.month_attendance.absent} absent · ${data.month_attendance.on_leave} on leave`} />
          <Link to="/payslips" className="block">
            <Kpi label="Last payslip" value={data.last_payslip ? fmtMoney(data.last_payslip.net) : '—'} tone="violet" icon={<FileText className="size-4" />}
              hint={data.last_payslip ? `Net pay · ${data.last_payslip.period}` : 'No finalized payslip yet'} />
          </Link>
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <Card title={`Leave balance ${data.leave_balance.year}`} action={<Link to="/me/leave"><Button size="sm" variant="secondary">Apply for leave</Button></Link>}>
            <ul className="space-y-3">
              {data.leave_balance.balances.map((b) => (
                <li key={b.code}>
                  <div className="flex justify-between text-sm">
                    <span>{b.name}</span>
                    <span className="tabular text-muted">{b.quota === null ? `${b.used} used · unlimited` : `${b.remaining} of ${b.quota} left`}{b.pending ? ` · ${b.pending} pending` : ''}</span>
                  </div>
                  {b.quota !== null && (
                    <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                      <div className="h-full rounded-full bg-teal" style={{ width: `${Math.min(100, (b.used / Math.max(b.quota, 1)) * 100)}%` }} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
          <AnnouncementsCard />
        </div>
        <p className="text-xs text-muted">Tip: ask the assistant (bottom right) things like “How many sick leaves do I have left?” — it only sees your own data.</p>
      </div>
    </>
  )
}

export function DashboardPage() {
  const user = useUser()
  if (user.role === 'admin') return <AdminDashboard />
  if (user.role === 'hr') return <HRDashboard />
  return <EmployeeDashboard />
}
