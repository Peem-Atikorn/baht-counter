import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { USE_MOCK } from './api/client'
import Capture from './pages/Capture'
import Home from './pages/Home'
import Result from './pages/Result'

export default function App() {
  return (
    <BrowserRouter>
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-2xl items-center justify-between px-4 py-3">
          <Link to="/" className="font-semibold">฿ นับเหรียญ</Link>
          {USE_MOCK && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">mock API</span>}
          {/* TODO(ส่วนที่ 5, สัปดาห์ 4): ลิงก์ประวัติ และ เกี่ยวกับ */}
        </nav>
      </header>
      <main className="mx-auto max-w-2xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/count" element={<Capture />} />
          <Route path="/result/:id" element={<Result />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
