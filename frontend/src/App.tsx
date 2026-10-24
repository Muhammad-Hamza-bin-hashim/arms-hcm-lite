import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Layout } from './components/Layout'
import { EmptyState, ErrorState, Spinner } from './components/ui'
import { api } from './lib/api'
import { useAuth } from './lib/auth'
import type { Role } from './lib/types'
import { ForcedChangePasswordPage, LoginPage, SetupPage } from './pages/auth/AuthPages'

// Each area loads on demand, so the first screen downloads only what it needs.
const m = <T,>(load: () => Promise<T>, pick: (mod: T) => ComponentType) => lazy(() => load().then((mod) => ({ default: pick(mod) })))
const org = () => import('./pages/admin/Organization')
const users = () => import('./pages/admin/Users')
const att = () => import('./pages/attendance/Attendance')
const dash = () => import('./pages/dashboards/Dashboards')
const emp = () => import('./pages/employees/Employees')
const leave = () => import('./pages/leave/Leave')
const misc = () => import('./pages/misc/Misc')
const pay = () => import('./pages/payroll/Payroll')
const OrganizationPage = m(org, (x) => x.OrganizationPage)
const UsersPage = m(users, (x) => x.UsersPage)
const AttendanceBoardPage = m(att, (x) => x.AttendanceBoardPage)
const CorrectionsPage = m(att, (x) => x.CorrectionsPage)
const MyAttendancePage = m(att, (x) => x.MyAttendancePage)
const DashboardPage = m(dash, (x) => x.DashboardPage)
const CsvImportPage = m(emp, (x) => x.CsvImportPage)
const Employee360Page = m(emp, (x) => x.Employee360Page)
const EmployeesPage = m(emp, (x) => x.EmployeesPage)
const LeaveRequestsPage = m(leave, (x) => x.LeaveRequestsPage)
const MyLeavePage = m(leave, (x) => x.MyLeavePage)
const AILogsPage = m(misc, (x) => x.AILogsPage)
const AnnouncementsPage = m(misc, (x) => x.AnnouncementsPage)
const AuditLogPage = m(misc, (x) => x.AuditLogPage)
const ProfilePage = m(misc, (x) => x.ProfilePage)
const PayrollRunDetailPage = m(pay, (x) => x.PayrollRunDetailPage)
const PayrollRunsPage = m(pay, (x) => x.PayrollRunsPage)
const PayslipsPage = m(pay, (x) => x.PayslipsPage)
const SalariesPage = m(pay, (x) => x.SalariesPage)

function Guard({ roles, profile, children }: { roles?: Role[]; profile?: boolean; children: ReactNode }) {
  const { user } = useAuth()
  if (!user) return null
  if ((roles && !roles.includes(user.role)) || (profile && !user.employee_id)) {
    return <EmptyState title="Not available for your role" body="This page is not part of your workspace." />
  }
  return <>{children}</>
}

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<Spinner />}>{children}</Suspense>
}

export default function App() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const setup = useQuery({ queryKey: ['setup-status'], queryFn: () => api.get<{ setup_completed: boolean; company_name: string }>('/setup/status/'), staleTime: 60_000 })

  if (setup.isLoading || loading) return <div className="flex h-full items-center justify-center"><Spinner /></div>
  if (setup.error) return <div className="flex h-full items-center justify-center"><ErrorState error={setup.error} retry={setup.refetch} /></div>
  if (!setup.data?.setup_completed) {
    return <Routes><Route path="*" element={<SetupPage />} /></Routes>
  }
  if (!user) {
    return <Routes><Route path="/login" element={<LoginPage />} /><Route path="*" element={<Navigate to="/login" replace state={{ from: location }} />} /></Routes>
  }
  if (user.must_change_password) {
    return <Routes><Route path="*" element={<ForcedChangePasswordPage />} /></Routes>
  }
  const staff: Role[] = ['admin', 'hr']
  return (
    <Routes>
      <Route element={<Layout><Page><Outlet /></Page></Layout>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/employees" element={<Guard roles={staff}><EmployeesPage /></Guard>} />
        <Route path="/employees/import" element={<Guard roles={['hr']}><CsvImportPage /></Guard>} />
        <Route path="/employees/:id" element={<Employee360Page />} />
        <Route path="/attendance" element={<Guard roles={staff}><AttendanceBoardPage /></Guard>} />
        <Route path="/attendance/corrections" element={<Guard roles={staff}><CorrectionsPage /></Guard>} />
        <Route path="/leave/requests" element={<Guard roles={staff}><LeaveRequestsPage /></Guard>} />
        <Route path="/leave/approvals" element={<Navigate to="/leave/requests?status=pending" replace />} />
        <Route path="/me/attendance" element={<Guard profile><MyAttendancePage /></Guard>} />
        <Route path="/me/leave" element={<Guard profile><MyLeavePage /></Guard>} />
        <Route path="/attendance/me" element={<Navigate to="/me/attendance" replace />} />
        <Route path="/leave" element={<Navigate to={user.role === 'employee' ? '/me/leave' : '/leave/requests'} replace />} />
        <Route path="/salaries" element={<Guard roles={staff}><SalariesPage /></Guard>} />
        <Route path="/payroll" element={<Guard roles={staff}><PayrollRunsPage /></Guard>} />
        <Route path="/payroll/:id" element={<Guard roles={staff}><PayrollRunDetailPage /></Guard>} />
        <Route path="/payslips" element={<PayslipsPage />} />
        <Route path="/announcements" element={<AnnouncementsPage />} />
        <Route path="/settings" element={<Guard roles={staff}><OrganizationPage /></Guard>} />
        <Route path="/users" element={<Guard roles={['admin']}><UsersPage /></Guard>} />
        <Route path="/audit" element={<Guard roles={['admin']}><AuditLogPage /></Guard>} />
        <Route path="/ai-logs" element={<Guard roles={['admin']}><AILogsPage /></Guard>} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}
