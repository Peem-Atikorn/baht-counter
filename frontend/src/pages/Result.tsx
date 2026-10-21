import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  addCoin,
  deleteCoin,
  exportAnalysis,
  getAnalysis,
  getCoinTypes,
  imageUrl,
  updateCoin,
  type AnalysisResponse,
  type Coin,
  type CoinCode,
  type CoinTypeInfo,
  type ExportFormat,
} from '../api/client'
import CoinOverlay from '../components/CoinOverlay'
import { baht, STATUS_TH } from '../lib/format'
import { saveDownload } from '../lib/download'

type EditorProps = {
  coin: Coin
  displayNumber: number
  types: CoinTypeInfo[]
  busy: boolean
  onSave: (code: CoinCode) => void
  onDelete: () => void
  onClose: () => void
}
function CoinEditor({ coin, displayNumber, types, busy, onSave, onDelete, onClose }: EditorProps) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [code, setCode] = useState<CoinCode | ''>(coin.coin_type ?? '')
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <section className="coin-editor" aria-labelledby="editor-heading">
      <div className="section-heading">
        <h3 id="editor-heading" ref={heading} tabIndex={-1}>
          แก้เหรียญ {displayNumber}
        </h3>
        <button disabled={busy} className="text-button" onClick={onClose}>
          ปิด
        </button>
      </div>
      {coin.reason && <p>{coin.reason}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (code && !busy) onSave(code)
        }}
      >
        <label htmlFor="coin-type">ชนิดเหรียญ</label>
        <select
          id="coin-type"
          value={code}
          disabled={busy}
          onChange={(event) => setCode(event.target.value as CoinCode)}
        >
          <option value="" disabled>
            เลือกชนิดเหรียญ
          </option>
          {types
            .filter((t) => t.code !== 'unknown')
            .map((t) => (
              <option key={t.code} value={t.code}>
                {t.name_th}
              </option>
            ))}
          <option value="unknown">ไม่ใช่เหรียญไทย / ระบุไม่ได้</option>
        </select>
        <p className="field-hint">
          การยืนยันเหรียญไทยที่ตรวจขนาดได้ จะช่วยคำนวณชนิดของเหรียญอื่นในภาพใหม่
        </p>
        <button className="primary-button" disabled={busy || !code} type="submit">
          {busy ? 'กำลังบันทึก…' : 'ยืนยันชนิดเหรียญ'}
        </button>
      </form>
      {confirmDelete ? (
        <div className="delete-confirm">
          <p>ลบเหรียญนี้ออกจากผลการนับ?</p>
          <button className="danger-button" disabled={busy} onClick={onDelete}>
            ยืนยันลบเหรียญ
          </button>
          <button className="text-button" disabled={busy} onClick={() => setConfirmDelete(false)}>
            ยกเลิก
          </button>
        </div>
      ) : (
        <button
          className="text-button danger-text"
          disabled={busy}
          onClick={() => setConfirmDelete(true)}
        >
          ลบเหรียญนี้
        </button>
      )}
    </section>
  )
}

export default function Result() {
  const { id = '' } = useParams()
  const [loaded, setLoaded] = useState<{ data: AnalysisResponse; types: CoinTypeInfo[] } | null>(
    null,
  )
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [editError, setEditError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const [x, setX] = useState('')
  const [y, setY] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([getAnalysis(id), getCoinTypes()])
      .then(([data, types]) => {
        if (active) setLoaded({ data, types })
      })
      .catch((error) => {
        if (active) setLoadError(error instanceof Error ? error.message : 'โหลดผลไม่สำเร็จ')
      })
    return () => {
      active = false
    }
  }, [id, reload])

  async function change(
    action: () => Promise<AnalysisResponse>,
    kind: 'update' | 'add' | 'delete',
  ) {
    if (inFlight.current || !loaded) return
    inFlight.current = true
    setBusy(true)
    setEditError(null)
    setAnnouncement('')
    try {
      const response = await action()
      setLoaded({ data: response, types: loaded.types })
      if (kind === 'add') {
        const added = response.result.coins.find(
          (c) => !loaded.data.result.coins.some((old) => old.coin_id === c.coin_id),
        )
        setSelectedId(added?.coin_id ?? null)
        setAdding(false)
      } else if (kind === 'delete') setSelectedId(null)
      setAnnouncement(
        kind === 'delete'
          ? 'ลบเหรียญและปรับยอดรวมแล้ว'
          : kind === 'add'
            ? 'เพิ่มเหรียญแล้ว กรุณาเลือกชนิด'
            : 'บันทึกชนิดเหรียญและปรับผลการนับแล้ว',
      )
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'บันทึกไม่สำเร็จ กรุณาลองใหม่')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  async function download(format: ExportFormat) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setEditError(null)
    try {
      saveDownload(await exportAnalysis(id, format), `${id}.${format}`)
      setAnnouncement('เตรียมไฟล์ดาวน์โหลดแล้ว')
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'ดาวน์โหลดไม่สำเร็จ')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  if (loadError)
    return (
      <div className="content-card">
        <p role="alert">{loadError}</p>
        <button
          className="primary-button"
          onClick={() => {
            setLoadError(null)
            setReload((n) => n + 1)
          }}
        >
          ลองอีกครั้ง
        </button>
        <Link className="text-button" to="/history">
          กลับประวัติ
        </Link>
      </div>
    )
  if (!loaded) return <p role="status">กำลังโหลดผลการนับ…</p>
  const { data, types } = loaded
  const r = data.result
  const [w, h] = r.image_size
  const selected = r.coins.find((c) => c.coin_id === selectedId)
  const rows = types
    .filter((t) => t.code !== 'unknown')
    .map((t) => ({ t, n: r.coins.filter((c) => c.coin_type === t.code).length }))
    .filter((row) => row.n > 0)
  const unresolved = r.coins.filter((c) => !c.coin_type).length
  const notThai = r.coins.filter((c) => c.coin_type === 'unknown').length
  const displayStatus = r.status === 'ok' && r.total_baht == null ? 'needs_confirmation' : r.status
  const statusLabel =
    displayStatus === 'needs_confirmation' && r.total_baht == null
      ? 'ยังรวมยอดไม่ได้'
      : STATUS_TH[displayStatus]
  const addAt = (xy: [number, number]) => {
    void change(() => addCoin(id, xy), 'add')
  }
  return (
    <div className="result-page space-y-4">
      <div className="section-heading">
        <h2>ตรวจผลการนับ</h2>
        <Link className="text-button" to="/history">
          ประวัติ
        </Link>
      </div>
      <p className={`result-status status-${displayStatus}`}>
        {statusLabel}
        {r.reason ? ` · ${r.reason}` : ''}
      </p>
      <p>เลือกวงเหรียญบนภาพ หรือเลือกจากรายการด้านล่างเพื่อยืนยันชนิด</p>
      <div className="result-toolbar">
        <button
          className={`secondary-button ${adding ? 'is-active' : ''}`}
          aria-pressed={adding}
          disabled={busy || imageFailed}
          onClick={() => {
            setAdding(!adding)
            setSelectedId(null)
            setX('')
            setY('')
          }}
        >
          {adding ? 'ยกเลิกเพิ่มเหรียญ' : 'เพิ่มเหรียญที่ยังไม่ถูกนับ'}
        </button>
        <Link className="text-button" to={`/about?analysis=${encodeURIComponent(id)}`}>
          ดูขั้นตอนประมวลผล
        </Link>
      </div>
      {imageFailed ? (
        <p role="alert">โหลดภาพไม่ได้ กรุณาเปิดผลการนับใหม่จากประวัติ</p>
      ) : (
        <div className="coin-stage" style={{ aspectRatio: `${w} / ${h}` }}>
          <img
            src={imageUrl(data.analysis_id, 'original')}
            alt="ภาพที่นับ"
            onError={() => setImageFailed(true)}
          />
          <CoinOverlay
            result={r}
            types={types}
            selectedId={selectedId}
            adding={adding}
            busy={busy}
            onSelect={(coin) => {
              setSelectedId(coin.coin_id)
              setAdding(false)
            }}
            onAdd={addAt}
          />
        </div>
      )}
      {adding && (
        <form
          className="add-coin-form"
          onSubmit={(event) => {
            event.preventDefault()
            const xy: [number, number] = [Number(x), Number(y)]
            if (
              !x.trim() ||
              !y.trim() ||
              xy.some((v) => !Number.isFinite(v)) ||
              xy[0] < 0 ||
              xy[1] < 0 ||
              xy[0] >= w ||
              xy[1] >= h
            ) {
              setEditError('กรุณาระบุพิกัดที่อยู่ภายในภาพ')
              return
            }
            addAt(xy)
          }}
        >
          <p>กดที่ตำแหน่งเหรียญบนภาพ หรือระบุพิกัดภาพต้นฉบับด้านล่าง</p>
          <div className="coordinate-fields">
            <label>
              พิกัด X (พิกเซล)
              <input
                required
                type="number"
                min="0"
                max={w - 1}
                step="any"
                value={x}
                disabled={busy}
                onChange={(event) => setX(event.target.value)}
              />
            </label>
            <label>
              พิกัด Y (พิกเซล)
              <input
                required
                type="number"
                min="0"
                max={h - 1}
                step="any"
                value={y}
                disabled={busy}
                onChange={(event) => setY(event.target.value)}
              />
            </label>
          </div>
          <button className="secondary-button" disabled={busy}>
            เพิ่มที่พิกัดนี้
          </button>
        </form>
      )}
      <div role="status" aria-live="polite">
        {busy ? 'กำลังดำเนินการ…' : announcement}
      </div>
      {editError && (
        <p role="alert" className="error-message">
          {editError}
        </p>
      )}
      {selected && (
        <CoinEditor
          key={`${selected.coin_id}-${selected.coin_type}`}
          coin={selected}
          displayNumber={r.coins.findIndex((c) => c.coin_id === selected.coin_id) + 1}
          types={types}
          busy={busy}
          onSave={(code) => {
            void change(() => updateCoin(id, selected.coin_id, code), 'update')
          }}
          onDelete={() => {
            void change(() => deleteCoin(id, selected.coin_id), 'delete')
          }}
          onClose={() => setSelectedId(null)}
        />
      )}
      <div className="total-card">
        <p>ยอดรวม</p>
        <strong>{baht(r.total_baht)}</strong>
        <p>{r.coins.length} เหรียญ</p>
        {r.total_baht == null && notThai > 0 && (
          <p>มีวัตถุที่ไม่ใช่เหรียญไทย {notThai} ชิ้น ลบออกเพื่อรวมยอด</p>
        )}
        {r.total_baht == null && unresolved > 0 && (
          <p>มีเหรียญที่ยังไม่ทราบชนิด {unresolved} เหรียญ เลือกชนิดเพื่อรวมยอด</p>
        )}
      </div>
      <table className="summary-table">
        <caption className="sr-only">จำนวนและมูลค่าแยกตามชนิดเหรียญ</caption>
        <thead>
          <tr>
            <th scope="col">ชนิด</th>
            <th scope="col">จำนวน</th>
            <th scope="col">มูลค่า</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ t, n }) => (
            <tr key={t.code}>
              <th scope="row">{t.name_th}</th>
              <td>{n}</td>
              <td>{baht(n * t.value_baht)}</td>
            </tr>
          ))}
          {unresolved > 0 && (
            <tr>
              <th scope="row">ยังไม่ทราบชนิด</th>
              <td>{unresolved}</td>
              <td>ระบุไม่ได้</td>
            </tr>
          )}
          {notThai > 0 && (
            <tr>
              <th scope="row">ไม่ใช่เหรียญไทย</th>
              <td>{notThai}</td>
              <td>ระบุไม่ได้</td>
            </tr>
          )}
        </tbody>
      </table>
      <section aria-labelledby="coin-list-heading">
        <h3 id="coin-list-heading">เหรียญแต่ละเหรียญ</h3>
        <ul className="coin-list">
          {r.coins.map((coin, index) => (
            <li key={coin.coin_id}>
              <button
                disabled={busy}
                aria-pressed={selectedId === coin.coin_id}
                onClick={() => {
                  setSelectedId(coin.coin_id)
                  setAdding(false)
                }}
              >
                <span>
                  เหรียญ {index + 1} ·{' '}
                  {types.find((t) => t.code === coin.coin_type)?.name_th ??
                    (coin.coin_type === 'unknown' ? 'ไม่ใช่เหรียญไทย' : 'ยังไม่ทราบชนิด')}
                </span>
                <span>
                  {coin.source === 'user_added'
                    ? 'เพิ่มเอง'
                    : coin.source === 'user_edited'
                      ? 'แก้ไขแล้ว'
                      : 'ผลจากระบบ'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
      <div className="result-toolbar">
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => {
            void download('json')
          }}
        >
          ดาวน์โหลด JSON
        </button>
        <button
          className="secondary-button"
          disabled={busy}
          onClick={() => {
            void download('csv')
          }}
        >
          ดาวน์โหลด CSV
        </button>
        <Link to="/count" className="primary-button">
          นับภาพใหม่
        </Link>
      </div>
    </div>
  )
}
