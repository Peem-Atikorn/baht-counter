// สัปดาห์ 1: แสดงยอดรวมและตารางจากผล — วงกลมบนภาพและการแก้ผลทำในสัปดาห์ 2–3
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getAnalysis, getCoinTypes, imageUrl, type AnalysisResponse, type CoinTypeInfo } from '../api/client'

function baht(v: number | null | undefined) {
  return v == null ? 'ระบุไม่ได้' : `${v.toLocaleString('th-TH', { maximumFractionDigits: 2 })} บาท`
}

export default function Result() {
  const { id = '' } = useParams()
  const [data, setData] = useState<AnalysisResponse | null>(null)
  const [types, setTypes] = useState<CoinTypeInfo[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getAnalysis(id), getCoinTypes()])
      .then(([a, t]) => {
        setData(a)
        setTypes(t)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'โหลดผลไม่สำเร็จ'))
  }, [id])

  if (error)
    return (
      <div className="space-y-4">
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">{error}</p>
        <Link to="/count" className="text-emerald-700 underline">นับภาพใหม่</Link>
      </div>
    )
  if (!data) return <p className="text-slate-500">กำลังโหลด…</p>

  const r = data.result
  const unresolved = r.coins.filter((c) => !c.coin_type).length
  const rows = types
    .map((t) => ({ t, n: r.coins.filter((c) => c.coin_type === t.code).length }))
    .filter((row) => row.n > 0)

  return (
    <div className="space-y-4">
      <img src={imageUrl(data.analysis_id, 'original')} alt="ภาพที่นับ" className="max-h-[50vh] w-full rounded-xl bg-slate-200 object-contain" />

      {r.status !== 'ok' && r.reason && (
        <p className={`rounded-lg p-3 text-sm ${r.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-800'}`}>{r.reason}</p>
      )}

      <div className="rounded-2xl bg-white p-5 text-center shadow-sm">
        <p className="text-sm text-slate-500">ยอดรวม</p>
        <p className="text-4xl font-bold">{baht(r.total_baht)}</p>
        <p className="mt-1 text-sm text-slate-500">{r.coins.length} เหรียญ</p>
      </div>

      <table className="w-full overflow-hidden rounded-xl bg-white text-sm shadow-sm">
        <thead className="bg-slate-100 text-left">
          <tr>
            <th className="p-3">ชนิด</th>
            <th className="p-3 text-right">จำนวน</th>
            <th className="p-3 text-right">มูลค่า</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ t, n }) => (
            <tr key={t.code} className="border-t border-slate-100">
              <td className="p-3">
                <span className="mr-2 inline-block h-3 w-3 rounded-full" style={{ background: t.display_color }} />
                {t.name_th}
              </td>
              <td className="p-3 text-right">{n}</td>
              <td className="p-3 text-right">{baht(n * t.value_baht)}</td>
            </tr>
          ))}
          {unresolved > 0 && (
            <tr className="border-t border-slate-100 text-amber-700">
              <td className="p-3">ยังไม่ทราบชนิด</td>
              <td className="p-3 text-right">{unresolved}</td>
              <td className="p-3 text-right">ระบุไม่ได้</td>
            </tr>
          )}
        </tbody>
      </table>

      <Link to="/count" className="block rounded-xl bg-emerald-600 py-3 text-center font-medium text-white">นับภาพใหม่</Link>
    </div>
  )
}
