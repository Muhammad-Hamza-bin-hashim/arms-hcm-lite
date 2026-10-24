import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Clock, LogIn, LogOut } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { fmtDate, fmtMinutes, fmtTime } from '../lib/format'
import type { AttendanceRecord } from '../lib/types'
import { CameraCheckIn } from './CameraCheckIn'
import { useToast } from './toast'
import { Alert, Button, Card, Skeleton, StatusBadge } from './ui'

export interface TodayInfo {
  has_profile: boolean
  date: string
  record: AttendanceRecord | null
  worked_minutes: number
  office_start: string
  grace_minutes: number
  camera_enabled: boolean
  office_radius_m: number
  is_working_day: boolean
}

export function CheckInWidget() {
  const qc = useQueryClient()
  const toast = useToast()
  const [camera, setCamera] = useState(false)
  const [, tick] = useState(0)
  const { data, isLoading, error } = useQuery({ queryKey: ['attendance-today'], queryFn: () => api.get<TodayInfo>('/attendance/today/') })
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 60_000); return () => clearInterval(t) }, [])

  const refresh = () => ['attendance-today', 'employee-dashboard', 'my-calendar', 'attendance-records'].forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
  const checkIn = useMutation({ mutationFn: () => api.post('/attendance/check-in/'), onSuccess: () => { refresh(); toast.success('Checked in. Have a good day!') }, onError: toast.error })
  const checkOut = useMutation({ mutationFn: () => api.post('/attendance/check-out/'), onSuccess: () => { refresh(); toast.success('Checked out.') }, onError: toast.error })
  const cameraIn = useMutation({
    mutationFn: (body: object) => api.post('/attendance/camera-check-in/', body),
    onSuccess: () => { setCamera(false); refresh(); toast.success('Camera check-in accepted.') },
    onError: toast.error,
  })

  if (isLoading) return <Card title="Today"><Skeleton className="h-24" /></Card>
  if (error || !data) return <Card title="Today"><Alert>{(error as Error)?.message ?? 'Could not load attendance.'}</Alert></Card>
  if (!data.has_profile) return null
  const rec = data.record
  const live = rec && !rec.check_out ? Math.max(0, Math.floor((Date.now() - new Date(rec.check_in).getTime()) / 60000)) : data.worked_minutes

  return (
    <Card title={<span className="flex items-center gap-2"><Clock className="size-4 text-teal" /> Today · {fmtDate(data.date)}</span>}
      action={rec && <StatusBadge status={rec.status} />}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="grid grid-cols-3 gap-6 text-sm">
          <div><p className="text-xs text-muted">Check in</p><p className="tabular mt-0.5 font-semibold">{fmtTime(rec?.check_in)}</p></div>
          <div><p className="text-xs text-muted">Check out</p><p className="tabular mt-0.5 font-semibold">{fmtTime(rec?.check_out)}</p></div>
          <div><p className="text-xs text-muted">Worked</p><p className="tabular mt-0.5 font-semibold">{rec ? fmtMinutes(live) : '—'}</p></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!rec && <>
            <Button variant="success" onClick={() => checkIn.mutate()} loading={checkIn.isPending}><LogIn className="size-4" /> Check in</Button>
            {data.camera_enabled && <Button variant="secondary" onClick={() => setCamera(true)}><Camera className="size-4" /> Camera</Button>}
          </>}
          {rec && !rec.check_out && <Button onClick={() => checkOut.mutate()} loading={checkOut.isPending}><LogOut className="size-4" /> Check out</Button>}
          {rec?.check_out && <p className="text-sm text-muted">Done for today.</p>}
        </div>
      </div>
      <p className="mt-3 text-xs text-muted">
        Office starts {data.office_start.slice(0, 5)} with {data.grace_minutes} min grace. The server records the exact time.
        {!data.is_working_day && ' Today is not a working day.'}
      </p>
      <CameraCheckIn open={camera} onClose={() => setCamera(false)} submitting={cameraIn.isPending}
        radius={data.office_radius_m} onSubmit={(d) => cameraIn.mutate(d)} />
    </Card>
  )
}
