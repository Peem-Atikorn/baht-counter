import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createAnalysis } from '../api/client'
import Camera from '../components/Camera'
import Icon from '../components/Icon'
import ProcessingStatus from '../components/ProcessingStatus'
import { IMAGE_ACCEPT, normalizeImage, validateImage } from '../lib/image'

type Preview = { image: Blob; url: string; from: 'camera' | 'upload'; failed?: boolean }

export default function Capture() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [cameraOpen, setCameraOpen] = useState(searchParams.get('source') === 'camera')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [sending, setSending] = useState(false)
  const inFlight = useRef(false)
  const uploadInput = useRef<HTMLInputElement>(null)
  const captureInput = useRef<HTMLInputElement>(null)

  // ใช้ source แค่ตอนเข้าหน้า เพื่อไม่เปิดกล้องซ้ำเมื่อรีเฟรชหรือย้อนกลับ
  useEffect(() => {
    if (!searchParams.has('source')) return
    const next = new URLSearchParams(searchParams)
    next.delete('source')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview.url)
    },
    [preview],
  )

  const choose = useCallback((image: Blob, from: Preview['from']) => {
    if (inFlight.current) return
    const problem = validateImage(image)
    if (problem) return setError(problem)
    setError(null)
    const original = normalizeImage(image)
    setPreview({ image: original, url: URL.createObjectURL(original), from })
  }, [])

  // วางภาพจากคลิปบอร์ด (Ctrl+V)
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const file = [...(e.clipboardData?.files ?? [])].find(
        (f) => f.type.startsWith('image/') || /\.hei[cf]$/i.test(f.name),
      )
      if (file) choose(file, 'upload')
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [choose])

  // click() บน input ต้องมาจากการกดของผู้ใช้ จึงแสดงปุ่มให้กดแทนการเปิดเอง
  const onCameraUnavailable = useCallback((reason: string) => {
    setCameraOpen(false)
    setNotice(reason)
  }, [])

  function onFileInput(e: React.ChangeEvent<HTMLInputElement>, from: Preview['from']) {
    const file = e.target.files?.[0]
    if (file) choose(file, from)
    e.target.value = ''
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) choose(file, 'upload')
  }

  function retake() {
    if (inFlight.current) return
    if (preview?.from !== 'camera') uploadInput.current?.click()
    else if (notice) captureInput.current?.click()
    else setCameraOpen(true)
  }

  async function send() {
    if (!preview || inFlight.current) return
    inFlight.current = true
    setSending(true)
    setError(null)
    try {
      const { analysis_id } = await createAnalysis(preview.image)
      navigate(`/result/${analysis_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ส่งภาพไม่สำเร็จ')
    } finally {
      inFlight.current = false
      setSending(false)
    }
  }

  return (
    <div className="capture-page space-y-4">
      <p className="eyebrow">ONE PHOTO. EVERY COIN.</p>
      <h2>เหรียญของคุณ มีค่าเท่าไร?</h2>
      <p className="text-sm text-copy-muted">
        วางเหรียญบนพื้นสีเรียบ ไม่ให้ซ้อนกัน แล้วถ่ายจากด้านบน
      </p>

      {notice && (
        <div className="flex items-center justify-between gap-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          <span>{notice}</span>
          <button
            disabled={sending}
            onClick={() => captureInput.current?.click()}
            className="shrink-0 rounded-lg bg-amber-600 px-3 py-2 text-white"
          >
            เปิดแอปกล้อง
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {preview ? (
        <div className="space-y-3">
          {preview.failed ? (
            <div role="status" className="rounded-xl bg-surface-muted p-6 text-center">
              <Icon name="upload" className="mx-auto mb-3" />
              <p>เบราว์เซอร์เปิดภาพตัวอย่างนี้ไม่ได้</p>
              <p className="mt-2 text-sm text-copy-muted">
                กด “ใช้รูปนี้” เพื่อส่งไฟล์ต้นฉบับให้นับเหรียญ หรือเลือกภาพใหม่
              </p>
            </div>
          ) : (
            <img
              key={preview.url}
              src={preview.url}
              alt="ภาพที่เลือก"
              onError={() =>
                setPreview((current) =>
                  current?.url === preview.url ? { ...current, failed: true } : current,
                )
              }
              className="max-h-[60vh] w-full rounded-xl bg-surface-muted object-contain"
            />
          )}
          {sending && <ProcessingStatus />}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={retake}
              disabled={sending}
              className="rounded-xl border border-outline py-3 font-medium"
            >
              {preview.from === 'camera' ? 'ถ่ายใหม่' : 'เลือกใหม่'}
            </button>
            <button
              onClick={send}
              disabled={sending}
              className="rounded-xl bg-brand py-3 font-medium text-white disabled:opacity-60"
            >
              {sending ? 'กำลังนับ…' : 'ใช้รูปนี้'}
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`upload-zone space-y-4 rounded-2xl border-2 border-dashed text-center ${dragging ? 'dragging' : ''}`}
        >
          <Icon name="scan" className="upload-art" />
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setCameraOpen(true)}
              className="rounded-xl bg-brand py-4 font-medium text-white"
            >
              <Icon name="camera" className="mx-auto mb-2" />
              ถ่ายรูป
            </button>
            <button
              onClick={() => uploadInput.current?.click()}
              className="rounded-xl bg-sage py-4 font-medium text-white"
            >
              <Icon name="upload" className="mx-auto mb-2" />
              อัปโหลดรูป
            </button>
          </div>
          <p className="hidden text-sm text-slate-500 sm:block">
            หรือลากไฟล์มาวางที่นี่ หรือกด Ctrl+V เพื่อวางภาพที่คัดลอกไว้
          </p>
          <p className="text-xs text-slate-500">JPEG, PNG, WebP, HEIC หรือ HEIF · ไม่เกิน 15 MB</p>
        </div>
      )}

      <input
        ref={uploadInput}
        type="file"
        accept={IMAGE_ACCEPT}
        disabled={sending}
        hidden
        onChange={(e) => onFileInput(e, 'upload')}
      />
      <input
        ref={captureInput}
        type="file"
        accept="image/*"
        capture="environment"
        disabled={sending}
        hidden
        onChange={(e) => onFileInput(e, 'camera')}
      />

      {cameraOpen && (
        <Camera
          onCapture={(img) => {
            setCameraOpen(false)
            choose(img, 'camera')
          }}
          onCancel={() => setCameraOpen(false)}
          onUnavailable={onCameraUnavailable}
        />
      )}
    </div>
  )
}
