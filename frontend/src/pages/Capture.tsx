import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createAnalysis } from '../api/client'
import Camera from '../components/Camera'
import { ACCEPTED_TYPES, validateImage } from '../lib/image'

type Preview = { image: Blob; url: string; from: 'camera' | 'upload' }

export default function Capture() {
  const navigate = useNavigate()
  const [cameraOpen, setCameraOpen] = useState(false)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [sending, setSending] = useState(false)
  const uploadInput = useRef<HTMLInputElement>(null)
  const captureInput = useRef<HTMLInputElement>(null)

  const choose = useCallback((image: Blob, from: Preview['from']) => {
    const problem = validateImage(image)
    if (problem) return setError(problem)
    setError(null)
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old.url)
      return { image, url: URL.createObjectURL(image), from }
    })
  }, [])

  // วางภาพจากคลิปบอร์ด (Ctrl+V)
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const file = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith('image/'))
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
    if (preview?.from !== 'camera') uploadInput.current?.click()
    else if (notice) captureInput.current?.click()
    else setCameraOpen(true)
  }

  async function send() {
    if (!preview) return
    setSending(true)
    setError(null)
    try {
      const { analysis_id } = await createAnalysis(preview.image)
      navigate(`/result/${analysis_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ส่งภาพไม่สำเร็จ')
      setSending(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">นับเหรียญ</h1>
      <p className="text-sm text-slate-600">วางเหรียญบนพื้นสีเรียบ ไม่ให้ซ้อนกัน แล้วถ่ายจากด้านบน</p>

      {notice && (
        <div className="flex items-center justify-between gap-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          <span>{notice}</span>
          <button onClick={() => captureInput.current?.click()} className="shrink-0 rounded-lg bg-amber-600 px-3 py-2 text-white">
            เปิดแอปกล้อง
          </button>
        </div>
      )}
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {preview ? (
        <div className="space-y-3">
          <img src={preview.url} alt="ภาพที่เลือก" className="max-h-[60vh] w-full rounded-xl bg-slate-200 object-contain" />
          <div className="grid grid-cols-2 gap-3">
            <button onClick={retake} disabled={sending} className="rounded-xl border border-slate-300 py-3 font-medium">
              {preview.from === 'camera' ? 'ถ่ายใหม่' : 'เลือกใหม่'}
            </button>
            <button onClick={send} disabled={sending} className="rounded-xl bg-emerald-600 py-3 font-medium text-white disabled:opacity-60">
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
          className={`space-y-4 rounded-2xl border-2 border-dashed p-6 text-center ${dragging ? 'border-emerald-500 bg-emerald-50' : 'border-slate-300'}`}
        >
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => setCameraOpen(true)} className="rounded-xl bg-emerald-600 py-4 font-medium text-white">
              ถ่ายรูป
            </button>
            <button onClick={() => uploadInput.current?.click()} className="rounded-xl bg-slate-800 py-4 font-medium text-white">
              อัปโหลดรูป
            </button>
          </div>
          <p className="hidden text-sm text-slate-500 sm:block">หรือลากไฟล์มาวางที่นี่ หรือกด Ctrl+V เพื่อวางภาพที่คัดลอกไว้</p>
        </div>
      )}

      <input ref={uploadInput} type="file" accept={ACCEPTED_TYPES.join(',')} hidden onChange={(e) => onFileInput(e, 'upload')} />
      <input ref={captureInput} type="file" accept="image/*" capture="environment" hidden onChange={(e) => onFileInput(e, 'camera')} />

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
