import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { CompanySettings, Department, Designation, LeaveType } from './types'

export const useDepartments = () =>
  useQuery({ queryKey: ['departments'], queryFn: () => api.get<Department[]>('/departments/'), staleTime: 60_000 })

export const useDesignations = () =>
  useQuery({ queryKey: ['designations'], queryFn: () => api.get<Designation[]>('/designations/'), staleTime: 60_000 })

/** Active leave types for forms (available to every role). */
export const useLeaveTypeOptions = () =>
  useQuery({ queryKey: ['leave-type-options'], queryFn: () => api.get<LeaveType[]>('/leave/types/'), staleTime: 60_000 })

export const useCompanySettings = (enabled = true) =>
  useQuery({ queryKey: ['settings'], queryFn: () => api.get<CompanySettings>('/settings/'), enabled, staleTime: 60_000 })
