import { useState } from 'react'
import { imageUrl, USE_MOCK, type CountResult } from '../api/client'

const LABELS: Record<string, string> = {
  gray: 'ภาพระดับสีเทา',
  clahe: 'ปรับความต่างระดับแสง',
  enhanced: 'ภาพหลังลดจุดรบกวน',
  detection_edges: 'ขอบเหรียญ',
  detection_distance: 'ระยะห่างจากขอบเหรียญ',
  detection_watershed: 'แยกเหรียญที่ชิดกัน',
  detection_result: 'ตำแหน่งเหรียญที่ตรวจพบ',
  edges: 'ขอบเหรียญ',
  mask: 'พื้นที่เหรียญ',
  detection_mask: 'พื้นที่เหรียญ',
  distance: 'ระยะห่างจากขอบ',
  distance_map: 'ระยะห่างจากขอบ',
  watershed: 'แยกเหรียญที่ชิดกัน',
  circles: 'ตำแหน่งเหรียญ',
  color: 'กลุ่มสีเหรียญ',
}

function DebugImage({ src, label }: { src: string; label: string }) {
  const [failed, setFailed] = useState(false)
  return (
    <figure className="debug-image">
      <figcaption>{label}</figcaption>
      {failed ? (
        <p role="status">โหลดภาพนี้ไม่ได้ กรุณาเปิดผลการนับใหม่</p>
      ) : (
        <img src={src} alt={label} loading="lazy" onError={() => setFailed(true)} />
      )}
    </figure>
  )
}

export default function DebugGallery({ id, result }: { id: string; result: CountResult }) {
  const entries = Object.entries(result.debug_images ?? {})
  return (
    <section className="debug-section" aria-labelledby="debug-heading">
      <h3 id="debug-heading">ภาพแต่ละขั้นตอน</h3>
      <p>เปรียบเทียบภาพต้นฉบับกับภาพระหว่างประมวลผลของภาพเดียวกัน</p>
      {entries.length === 0 && (
        <p role="status">
          {USE_MOCK
            ? 'โหมดทดลองไม่มีภาพขั้นตอนประมวลผล'
            : 'ผลการนับนี้ไม่มีภาพขั้นตอนประมวลผลบันทึกไว้'}
        </p>
      )}
      <div className="debug-grid">
        <DebugImage src={imageUrl(id, 'original')} label="ภาพต้นฉบับ" />
        {entries.map(([name, url]) => (
          <DebugImage
            key={`${id}-${name}-${url}`}
            src={url}
            label={LABELS[name] ?? `ขั้นตอน: ${name}`}
          />
        ))}
      </div>
    </section>
  )
}
