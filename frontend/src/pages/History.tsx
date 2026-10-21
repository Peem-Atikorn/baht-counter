import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHistory, USE_MOCK, type HistoryPage } from '../api/client'
import { baht, STATUS_TH, thaiDate } from '../lib/format'

const PAGE_SIZE = 12
export default function History() {
  const [offset, setOffset] = useState(0)
  const [retry, setRetry] = useState(0)
  const [loaded, setLoaded] = useState<{ offset: number; page: HistoryPage } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    getHistory(PAGE_SIZE, offset)
      .then((page) => {
        if (active) setLoaded({ offset, page })
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : 'โหลดประวัติไม่สำเร็จ')
      })
    return () => {
      active = false
    }
  }, [offset, retry])
  const page = loaded?.offset === offset ? loaded.page : null
  function go(next: number) {
    setError(null)
    setOffset(next)
  }
  return (
    <section className="content-card history-page">
      <div className="section-heading">
        <h2>เหรียญที่เคยนับ</h2>
        <Link className="text-button" to="/count">
          นับภาพใหม่
        </Link>
      </div>
      {USE_MOCK && (
        <p className="field-hint">โหมดทดลอง: ประวัติจะหายเมื่อรีเฟรชหน้า ข้อมูลนี้เป็นผลจำลอง</p>
      )}
      {error ? (
        <div>
          <p role="alert" className="error-message">
            {error}
          </p>
          <button
            className="secondary-button"
            onClick={() => {
              setError(null)
              setRetry((n) => n + 1)
            }}
          >
            ลองอีกครั้ง
          </button>
        </div>
      ) : !page ? (
        <p role="status">กำลังโหลดประวัติ…</p>
      ) : (
        <>
          {page.total === 0 ? (
            <div className="empty-state">
              <h3>ยังไม่มีภาพที่นับ</h3>
              <p>เริ่มจากถ่ายหรืออัปโหลดภาพแรกของคุณ</p>
              <Link to="/count" className="primary-button">
                เริ่มนับเหรียญ
              </Link>
            </div>
          ) : (
            <>
              <p className="field-hint">ทั้งหมด {page.total} รายการ</p>
              <ul className="history-list">
                {page.items.map((item) => (
                  <li key={item.analysis_id}>
                    <Link to={`/result/${encodeURIComponent(item.analysis_id)}`}>
                      <div>
                        <h3>{thaiDate(item.created_at)}</h3>
                        <p>
                          {item.coin_count} เหรียญ · {STATUS_TH[item.status]}
                        </p>
                      </div>
                      <strong>{baht(item.total_baht)}</strong>
                      <span>ดูผล →</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {page.items.length === 0 && <p>หน้านี้ไม่มีรายการแล้ว กรุณากลับหน้าก่อน</p>}
              <nav className="pagination" aria-label="หน้าประวัติ">
                <button
                  className="secondary-button"
                  disabled={offset === 0}
                  onClick={() => go(Math.max(0, offset - PAGE_SIZE))}
                >
                  ก่อนหน้า
                </button>
                <span>
                  หน้า {Math.floor(offset / PAGE_SIZE) + 1} /{' '}
                  {Math.max(1, Math.ceil(page.total / PAGE_SIZE))}
                </span>
                <button
                  className="secondary-button"
                  disabled={offset + PAGE_SIZE >= page.total}
                  onClick={() => go(offset + PAGE_SIZE)}
                >
                  ถัดไป
                </button>
              </nav>
            </>
          )}
        </>
      )}
    </section>
  )
}
