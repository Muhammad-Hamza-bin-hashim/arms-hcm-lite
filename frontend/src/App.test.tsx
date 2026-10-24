import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'
import { ToastProvider } from './components/toast'
import { tokens } from './lib/api'
import { AuthProvider } from './lib/auth'
import type { Role, User } from './lib/types'
import { mockServer, page } from './test/mockServer'

const user = (role: Role, extra: Partial<User> = {}): User => ({
  id: 1, email: `${role}@arms.test`, first_name: 'Test', last_name: role, full_name: `Test ${role}`, role,
  must_change_password: false, is_active: true, employee_id: role === 'employee' ? 7 : null, last_login: null,
  date_joined: '2026-10-01', ...extra,
})

const base = {
  'GET /api/setup/status/': { body: { setup_completed: true, company_name: 'AR&MS Management Company' } },
  'GET /api/notifications/': { body: { ...page([]), unread_count: 0 } },
  'GET /api/announcements/': { body: page([]) },
  'GET /api/attendance/today/': { body: { has_profile: false } },
}

function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider><AuthProvider><App /></AuthProvider></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function navLabels() {
  const nav = await screen.findByRole('navigation', { name: 'Main' })
  return within(nav).getAllByRole('link').map((a) => a.textContent)
}

describe('app shell', () => {
  it('shows first-run setup on a fresh install', async () => {
    mockServer({ 'GET /api/setup/status/': { body: { setup_completed: false, company_name: '' } } })
    renderApp('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Set up your company' })).toBeInTheDocument()
  })

  it('sends signed-out users to the login page and reports bad credentials', async () => {
    mockServer({ ...base, 'POST /api/auth/login/': { status: 401, body: { detail: 'Invalid email or password.' } } })
    renderApp('/payroll')
    await userEvent.type(await screen.findByLabelText(/^Email/), 'a@b.co')
    await userEvent.type(screen.getByLabelText(/^Password/), 'wrong-pass')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument()
  })

  it('forces a temporary-password user to change it first', async () => {
    tokens.set('a', 'r')
    mockServer({ ...base, 'GET /api/auth/me/': { body: user('employee', { must_change_password: true }) } })
    renderApp('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Choose a new password' })).toBeInTheDocument()
  })

  it('gives each role its own menu', async () => {
    tokens.set('a', 'r')
    mockServer({ ...base, 'GET /api/auth/me/': { body: user('employee') }, 'GET /api/dashboard/employee/': { body: { has_profile: false } } })
    const { unmount } = renderApp('/dashboard')
    const employeeNav = await navLabels()
    expect(employeeNav).toEqual(expect.arrayContaining(['Dashboard', 'Payslips', 'My attendance', 'My leave', 'Announcements']))
    expect(employeeNav).not.toContain('Employees')
    expect(employeeNav).not.toContain('Audit log')
    unmount()

    tokens.set('a', 'r')
    mockServer({ ...base, 'GET /api/auth/me/': { body: user('hr') } })
    const hr = renderApp('/announcements')
    const hrNav = await navLabels()
    expect(hrNav).toEqual(expect.arrayContaining(['Employees', 'Leave requests', 'Payroll runs', 'Organization']))
    expect(hrNav).not.toContain('Users & logins')
    expect(hrNav).not.toContain('Audit log')
    expect(hrNav).not.toContain('My leave') // HR login without an employee profile
    hr.unmount()

    tokens.set('a', 'r')
    mockServer({ ...base, 'GET /api/auth/me/': { body: user('admin') } })
    renderApp('/announcements')
    expect(await navLabels()).toEqual(expect.arrayContaining(['Users & logins', 'Audit log', 'AI logs']))
  })

  it('blocks a page that is not part of the role', async () => {
    tokens.set('a', 'r')
    mockServer({ ...base, 'GET /api/auth/me/': { body: user('employee') } })
    renderApp('/audit')
    expect(await screen.findByText('Not available for your role')).toBeInTheDocument()
  })
})
