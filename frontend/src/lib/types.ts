export type Role = 'admin' | 'hr' | 'employee'

export interface User {
  id: number
  email: string
  first_name: string
  last_name: string
  full_name: string
  role: Role
  must_change_password: boolean
  is_active: boolean
  employee_id: number | null
  last_login: string | null
  date_joined: string
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Department { id: number; name: string; code: string; is_active: boolean; employee_count?: number }
export interface Designation { id: number; name: string; is_active: boolean }
export interface LeaveType { id: number; code: string; name: string; yearly_quota: number | null; is_paid: boolean; is_active?: boolean }
export interface Holiday { id: number; date: string; name: string }

export interface CompanySettings {
  company_name: string
  timezone: string
  currency: string
  office_start: string
  office_end: string
  grace_minutes: number
  half_day_hours: string
  weekend_days: number[]
  office_lat: string | null
  office_lng: string | null
  office_radius_m: number
  late_penalty_enabled: boolean
  updated_at: string
}

export interface Employee {
  id: number
  employee_code: string
  first_name: string
  last_name: string
  full_name: string
  email: string
  phone: string
  address: string
  gender: string
  date_of_birth: string | null
  department: number
  department_name: string
  designation: number | null
  designation_name: string | null
  join_date: string
  exit_date: string | null
  employment_status: 'probation' | 'active' | 'exited'
  user_id: number
  is_login_active: boolean
}

export interface AttendanceRecord {
  id: number
  employee: number
  employee_name: string
  employee_code: string
  date: string
  check_in: string
  check_out: string | null
  status: string
  is_late: boolean
  worked_minutes: number | null
  source: string
  distance_m: number | null
}

export interface AttendanceSummary {
  present: number
  late: number
  half_day: number
  missing_checkout: number
  on_leave: number
  absent: number
  not_marked: number
  late_arrivals: number
  working_day_records: number
  expected_working_days: number
  attendance_rate: number | null
  late_pct: number | null
  absenteeism_pct: number | null
  unpaid_leave_days: number
}

export interface LeaveRequest {
  id: number
  employee: number
  employee_name: string
  employee_code: string
  department: string
  leave_type: number
  leave_type_name: string
  leave_type_code: string
  start_date: string
  end_date: string
  days: number
  reason: string
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  source: 'form' | 'ai'
  decided_by_name: string | null
  decided_at: string | null
  decision_comment: string
  created_at: string
}

export interface Balance {
  leave_type_id: number
  code: string
  name: string
  is_paid: boolean
  quota: number | null
  used: number
  pending: number
  remaining: number | null
}

export interface PayrollRun {
  id: number
  year: number
  month: number
  period: string
  status: 'draft' | 'finalized'
  working_days: number
  employee_count: number
  total_gross: string
  total_deductions: string
  total_tax: string
  total_net: string
  created_by_name: string | null
  created_at: string
  generated_at: string | null
  finalized_by_name: string | null
  finalized_at: string | null
}

export interface Payslip {
  id: number
  run: number
  period: string
  run_status: string
  employee: number
  employee_code: string
  employee_name: string
  department_name: string
  designation_name: string
  basic: string
  hra: string
  medical: string
  gross: string
  working_days: number
  payable_days: number
  absent_days: string
  unpaid_leave_days: string
  half_days: string
  late_count: number
  late_penalty_days: string
  per_day_rate: string
  prorated_gross: string
  deduction: string
  earned_gross: string
  annual_taxable: string
  annual_tax: string
  tax: string
  net: string
}

export interface Notification {
  id: number
  kind: string
  title: string
  body: string
  link: string
  is_read: boolean
  created_at: string
}

export interface Announcement {
  id: number
  title: string
  body: string
  created_by_name: string
  created_by_role: Role
  created_at: string
}
