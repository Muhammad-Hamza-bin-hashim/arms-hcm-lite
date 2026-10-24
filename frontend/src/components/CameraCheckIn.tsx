import { CheckCircle2, Loader2, MapPin, ScanFace, XCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, cx, Modal } from './ui'

const WASM = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1/wasm'
const MODEL = 'https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite'

type Geo = { latitude: number; longitude: number; accuracy: number }

/**
 * Bonus camera attendance: detects faces in the browser (MediaPipe) and reads GPS.
 * Only the face count and coordinates are sent; the server checks the geofence and sets the time.
 * No image ever leaves the device.
 */
export function CameraCheckIn({ open, onClose, onSubmit, submitting, radius }:
  { open: boolean; onClose: () => void; onSubmit: (d: Geo & { face_count: number }) => void; submitting: boolean; radius: number }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [faces, setFaces] = useState<number | null>(null)
  const [geo, setGeo] = useState<Geo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!open) return
    let stream: MediaStream | null = null
    let raf = 0
    let cancelled = false
    let detector: { detectForVideo: (v: HTMLVideoElement, t: number) => { detections: unknown[] }; close: () => void } | null = null
    setFaces(null); setGeo(null); setError(null); setLoading(true)

    navigator.geolocation?.getCurrentPosition(
      (p) => !cancelled && setGeo({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy: p.coords.accuracy }),
      () => !cancelled && setError('Location permission is needed for camera check-in.'),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )

    ;(async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 640, height: 480 }, audio: false })
        if (cancelled || !videoRef.current) return
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        const vision = await import('@mediapipe/tasks-vision')
        const fileset = await vision.FilesetResolver.forVisionTasks(WASM)
        detector = await vision.FaceDetector.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODEL }, runningMode: 'VIDEO', minDetectionConfidence: 0.6,
        }) as unknown as typeof detector
        if (cancelled) return
        setLoading(false)
        let last = 0
        const loop = (now: number) => {
          const v = videoRef.current
          if (v && detector && v.readyState >= 2 && now - last > 250) {
            last = now
            setFaces(detector.detectForVideo(v, now).detections.length)
          }
          raf = requestAnimationFrame(loop)
        }
        raf = requestAnimationFrame(loop)
      } catch (e) {
        if (!cancelled) {
          setLoading(false)
          setError(e instanceof DOMException && e.name === 'NotAllowedError'
            ? 'Camera permission was denied. Allow camera access or use the normal check-in.'
            : 'Camera or face detection is not available on this device. Use the normal check-in.')
        }
      }
    })()

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      detector?.close()
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [open])

  const faceOk = faces === 1
  const geoOk = geo !== null && geo.accuracy <= 100
  return (
    <Modal open={open} onClose={onClose} title="Camera check-in"
      footer={<>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="success" disabled={!faceOk || !geo} loading={submitting}
          onClick={() => geo && faces !== null && onSubmit({ ...geo, face_count: faces })}>Check in</Button>
      </>}>
      <div className="space-y-3">
        <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-navy">
          <video ref={videoRef} playsInline muted className="size-full -scale-x-100 object-cover" />
          {loading && <div className="absolute inset-0 flex items-center justify-center text-sm text-white/80"><Loader2 className="mr-2 size-4 animate-spin" /> Starting camera…</div>}
          <div className={cx('pointer-events-none absolute inset-8 rounded-[40%] border-2', faceOk ? 'border-[#14B8A6]' : 'border-white/40')} />
        </div>
        <ul className="space-y-1.5 text-sm">
          <Check ok={faceOk} icon={<ScanFace className="size-4" />}
            text={faces === null ? 'Looking for your face…' : faces === 0 ? 'No face detected' : faces > 1 ? `${faces} faces detected — only you should be in frame` : 'Face detected'} />
          <Check ok={geoOk} icon={<MapPin className="size-4" />}
            text={!geo ? 'Getting your location…' : `Location accuracy ${Math.round(geo.accuracy)} m${geo.accuracy > 100 ? ' (must be 100 m or better)' : ''}`} />
        </ul>
        {error && <Alert tone="amber">{error}</Alert>}
        <p className="text-xs text-muted">Privacy: no photo is taken or stored. Only the number of faces and your GPS position are sent. The server checks that you are within {radius} m of the office and records the time itself.</p>
      </div>
    </Modal>
  )
}

function Check({ ok, text, icon }: { ok: boolean; text: string; icon: React.ReactNode }) {
  return (
    <li className={cx('flex items-center gap-2', ok ? 'text-teal' : 'text-muted')}>
      {icon}{text}{ok ? <CheckCircle2 className="ml-auto size-4" /> : <XCircle className="ml-auto size-4 opacity-40" />}
    </li>
  )
}
