import { Link } from 'react-router-dom'

export default function Home() {
  return (
    <div className="space-y-6 py-8 text-center">
      <h1 className="text-3xl font-bold">นับเหรียญไทย</h1>
      <p className="text-slate-600">
        ถ่ายหรืออัปโหลดภาพเหรียญที่วางบนพื้นราบ ระบบจะหาเหรียญ บอกชนิด และรวมยอดเงินให้ ถ้าอ่านผิดก็แก้บนหน้าเว็บได้
      </p>
      <Link to="/count" className="inline-block rounded-xl bg-emerald-600 px-8 py-4 text-lg font-medium text-white">
        เริ่มนับเหรียญ
      </Link>
    </div>
  )
}
