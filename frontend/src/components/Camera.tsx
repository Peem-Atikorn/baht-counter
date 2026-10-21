import { useEffect, useRef, useState } from 'react'
import { captureFrame } from '../lib/image'

type Props = {
  onCapture: (image: Blob) => void
  onCancel: () => void
  /** เรียกเมื่อเปิดกล้องในหน้าเว็บไม่ได้ ให้หน้าแม่ใช้ <input capture> แทน */
  onUnavailable: (reason: string) => void
}

function unavailableReason(err: unknown): string {
  if (!window.isSecureContext)
    return 'เปิดกล้องในหน้าเว็บได้เฉพาะ HTTPS จึงเปิดแอปกล้องของเครื่องแทน'
  if (err instanceof DOMException && err.name === 'NotAllowedError')
    return 'ไม่ได้รับอนุญาตให้ใช้กล้อง จึงเปิดแอปกล้องของเครื่องแทน'
  if (err instanceof DOMException && err.name === 'NotFoundError') return 'ไม่พบกล้องในเครื่องนี้'
  return 'เปิดกล้องในหน้าเว็บไม่ได้ จึงเปิดแอปกล้องของเครื่องแทน'
}

export default function Camera({ onCapture, onCancel, onUnavailable }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [facing, setFacing] = useState<'environment' | 'user'>('environment')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let stream: MediaStream | undefined
    let cancelled = false
    if (!navigator.mediaDevices?.getUserMedia) {
      onUnavailable(unavailableReason(null))
      return
    }
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: facing, width: { ideal: 4096 }, height: { ideal: 4096 } },
        audio: false,
      })
      .then((s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop())
        stream = s
        videoRef.current!.srcObject = s
      })
      .catch((err) => !cancelled && onUnavailable(unavailableReason(err)))
    return () => {
      cancelled = true
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [facing, onUnavailable])

  async function shoot() {
    if (videoRef.current) onCapture(await captureFrame(videoRef.current))
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black text-white">
      <div className="relative flex-1 overflow-hidden">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          onLoadedMetadata={() => setReady(true)}
          className={`h-full w-full object-contain ${facing === 'user' ? '-scale-x-100' : ''}`}
        />
        {/* กรอบนำสายตา */}
        <div className="pointer-events-none absolute inset-8 rounded-2xl border-2 border-dashed border-white/70" />
        <p className="absolute inset-x-0 top-4 text-center text-sm drop-shadow">
          ถ่ายจากด้านบน ให้เห็นเหรียญครบทุกเหรียญ
        </p>
      </div>
      <div className="flex items-center justify-between px-6 py-5">
        <button onClick={onCancel} className="rounded-lg px-3 py-2">
          ยกเลิก
        </button>
        <button
          onClick={shoot}
          disabled={!ready}
          aria-label="ชัตเตอร์"
          className="h-16 w-16 rounded-full border-4 border-white bg-white/90 disabled:opacity-40"
        />
        <button
          onClick={() => {
            setReady(false)
            setFacing((f) => (f === 'environment' ? 'user' : 'environment'))
          }}
          className="rounded-lg px-3 py-2"
        >
          สลับกล้อง
        </button>
      </div>
    </div>
  )
}
