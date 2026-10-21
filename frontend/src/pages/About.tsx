import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Icon from '../components/Icon'
import DebugGallery from '../components/DebugGallery'
import { getAnalysis, type AnalysisResponse } from '../api/client'

function AnalysisProcess({ id }: { id: string }) {
  const [data, setData] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    getAnalysis(id)
      .then((response) => {
        if (active) setData(response)
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'โหลดภาพขั้นตอนไม่สำเร็จ')
      })
    return () => {
      active = false
    }
  }, [id, retry])
  if (error)
    return (
      <section>
        <p role="alert">{error}</p>
        <button
          className="secondary-button"
          onClick={() => {
            setError(null)
            setRetry((n) => n + 1)
          }}
        >
          ลองอีกครั้ง
        </button>
      </section>
    )
  if (!data) return <p role="status">กำลังโหลดภาพขั้นตอนประมวลผล…</p>
  return (
    <>
      <Link className="text-button" to={`/result/${encodeURIComponent(id)}`}>
        กลับผลการนับ
      </Link>
      <DebugGallery id={id} result={data.result} />
    </>
  )
}

export default function About() {
  const [params] = useSearchParams()
  const analysisId = params.get('analysis')
  return (
    <article className="about-page content-card">
      <p className="eyebrow">A GOOD PHOTO MAKES A DIFFERENCE</p>
      <h2>รูปพร้อม เหรียญก็นับง่าย</h2>
      <p>เตรียมภาพตามคำแนะนำนี้ แล้วถ่ายหรืออัปโหลดเพื่อดูผลการนับเหรียญไทยทั้ง 6 ชนิด</p>
      <div className="about-tips">
        <section>
          <Icon name="layers" />
          <h3>วางบนพื้นเรียบ</h3>
          <p>เลือกพื้นสีเดียว วางเหรียญให้เห็นครบ และหลีกเลี่ยงการซ้อนทับกัน</p>
        </section>
        <section>
          <Icon name="sun" />
          <h3>ให้แสงสม่ำเสมอ</h3>
          <p>หลีกเลี่ยงเงามืดและแสงสะท้อนบนเหรียญ ไม่ต้องเปิดแฟลชหากมีแสงเพียงพอ</p>
        </section>
        <section>
          <Icon name="camera" />
          <h3>ถ่ายจากด้านบน</h3>
          <p>ถือกล้องให้นิ่ง ให้เห็นขอบเหรียญชัด รองรับ JPEG, PNG และ WebP ขนาดไม่เกิน 15 MB</p>
        </section>
      </div>
      <h3>ระบบทำงานอย่างไร</h3>
      <p>
        ปรับคุณภาพภาพ → หาตำแหน่งเหรียญ → จัดกลุ่มสีและเทียบขนาด → จำแนกชนิดและรวมยอดเงิน
        หากระบบยังระบุชนิดไม่ได้ จะแสดงสถานะให้ยืนยันแทนการเดายอดเงิน
      </p>
      {analysisId ? (
        <AnalysisProcess key={analysisId} id={analysisId} />
      ) : (
        <div className="process-intro">
          <p>เปิดผลการนับที่เคยบันทึก เพื่อดูภาพกลางทางของภาพนั้น</p>
          <Link className="secondary-button" to="/history">
            เลือกภาพจากประวัติ
          </Link>
        </div>
      )}
      <Link to="/count" className="primary-button">
        พร้อมแล้ว เริ่มนับเหรียญ <Icon name="arrow" />
      </Link>
    </article>
  )
}
