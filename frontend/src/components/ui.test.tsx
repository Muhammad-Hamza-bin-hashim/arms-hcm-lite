import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { ConfirmDialog, ErrorState, Input, Pagination, StatusBadge, Table } from './ui'

describe('ui kit', () => {
  it('shows field errors accessibly', () => {
    render(<Input label="Email" error="A user with this email already exists." value="" onChange={() => {}} />)
    const input = screen.getByLabelText('Email')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('already exists')
  })

  it('renders the empty state when a table has no rows', () => {
    render(<Table rows={[]} rowKey={() => 1} columns={[{ key: 'a', header: 'A', cell: () => 'x' }]} />)
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('labels statuses in plain words', () => {
    render(<StatusBadge status="missing_checkout" />)
    expect(screen.getByText('Missing checkout')).toBeInTheDocument()
  })

  it('hides pagination for a single page and pages otherwise', async () => {
    const { rerender } = render(<Pagination page={1} count={5} onPage={() => {}} />)
    expect(screen.queryByLabelText('Next page')).toBeNull()
    const onPage = vi.fn()
    rerender(<Pagination page={1} count={45} onPage={onPage} />)
    expect(screen.getByText('1–20 of 45')).toBeInTheDocument()
    await userEvent.click(screen.getByLabelText('Next page'))
    expect(onPage).toHaveBeenCalledWith(2)
  })

  it('shows access denied without a retry button for 403', () => {
    render(<ErrorState error={new ApiError(403, 'You do not have permission to do that.')} retry={() => {}} />)
    expect(screen.getByText('Access denied')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('confirm dialog calls confirm and closes on Escape', async () => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(<ConfirmDialog open title="Finalize payroll?" body="Locks the month." confirmLabel="Finalize" onConfirm={onConfirm} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Finalize' }))
    expect(onConfirm).toHaveBeenCalled()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
