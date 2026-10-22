import { useEffect, useState } from 'react'

export default function ProcessingStatus() {
  const [wait, setWait] = useState<'normal' | 'slow' | 'long'>('normal')
  useEffect(() => {
    const slow = window.setTimeout(() => setWait('slow'), 15_000)
    const long = window.setTimeout(() => setWait('long'), 45_000)
    return () => {
      window.clearTimeout(slow)
      window.clearTimeout(long)
    }
  }, [])

  return (
    <div
      role="status"
      aria-label="สถานะการนับเหรียญ"
      aria-atomic="true"
      className="flex items-start gap-3 rounded-xl bg-surface-muted p-4"
    >
      <span
        aria-hidden="true"
        className="mt-1 h-5 w-5 shrink-0 rounded-full border-2 border-brand border-t-transparent motion-safe:animate-spin"
      />
      <div>
        <p className="font-medium">กำลังนับเหรียญจากภาพนี้</p>
        <p className="mt-1 text-sm text-copy-muted">
          {wait === 'normal'
            ? 'กำลังส่งภาพและรอผลการนับ กรุณารอสักครู่'
            : wait === 'slow'
              ? 'ใช้เวลานานกว่าปกติ ภาพขนาดใหญ่หรือการเชื่อมต่อช้าอาจทำให้รอเพิ่ม'
              : 'ระบบอาจกำลังเริ่มทำงานหลังพัก ซึ่งอาจใช้เวลานานกว่าหนึ่งนาที ขณะนี้ยังรอผลอยู่'}
        </p>
        <p className="mt-1 text-sm text-copy-muted">
          ไม่ต้องกดส่งซ้ำ ภาพที่เลือกยังเก็บไว้ หากส่งไม่สำเร็จจะลองใหม่ได้
        </p>
      </div>
    </div>
  )
}
