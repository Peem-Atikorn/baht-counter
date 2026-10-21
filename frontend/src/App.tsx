import {
  BrowserRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useParams,
  matchPath,
} from 'react-router-dom'
import { USE_MOCK } from './api/client'
import Icon from './components/Icon'
import Home from './pages/Home'
import Capture from './pages/Capture'
import Result from './pages/Result'
import About from './pages/About'
import History from './pages/History'

function ResultRoute() {
  const { id } = useParams()
  return <Result key={id} />
}

function Workspace() {
  const { pathname } = useLocation()
  const title =
    pathname === '/'
      ? 'พื้นที่เล็ก ๆ ของเงินเหรียญ'
      : pathname === '/count'
        ? 'เริ่มนับเหรียญ'
        : pathname === '/about'
          ? 'รู้จักการนับเหรียญ'
          : pathname === '/history'
            ? 'ประวัติการนับเหรียญ'
            : matchPath('/result/:id', pathname)
              ? 'ผลการนับเหรียญ'
              : 'ไม่พบหน้านี้'
  return (
    <div className="workspace">
      <a className="skip-link" href="#main">
        ข้ามไปเนื้อหา
      </a>
      <aside className="sidebar">
        <Link to="/" className="brand-mark" aria-label="Baht Counter หน้าแรก">
          ฿<span />
        </Link>
        <nav aria-label="เมนูหลัก">
          <NavLink to="/" end aria-label="หน้าแรก">
            <Icon name="home" />
            <span>หน้าแรก</span>
          </NavLink>
          <NavLink to="/count" aria-label="นับเหรียญ">
            <Icon name="scan" />
            <span>นับเหรียญ</span>
          </NavLink>
          <NavLink to="/history" aria-label="ประวัติ">
            <Icon name="history" />
            <span>ประวัติ</span>
          </NavLink>
          <NavLink to="/about" aria-label="วิธีใช้งาน">
            <Icon name="book" />
            <span>วิธีใช้งาน</span>
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <span>
            BAHT
            <br />
            COUNTER
          </span>
          <span className="sidebar-dot" />
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <Link to="/" className="wordmark">
            baht<span>counter.</span>
          </Link>
          <span className="topbar-caption">ทุกเหรียญ มีความหมาย</span>
          <Link className="help-link" to="/about" aria-label="ดูวิธีใช้งาน">
            <Icon name="help" />
          </Link>
        </header>
        <div className="page-heading">
          <div>
            <p className="eyebrow">YOUR EVERYDAY COIN COMPANION</p>
            <h1>{title}</h1>
          </div>
          <span className="mode-badge">
            <i />
            {USE_MOCK ? 'โหมดทดลอง · ผลจำลอง' : 'นับเหรียญไทย 6 ชนิด'}
          </span>
        </div>
        <main id="main">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/count" element={<Capture />} />
            <Route path="/result/:id" element={<ResultRoute />} />
            <Route path="/history" element={<History />} />
            <Route path="/about" element={<About />} />
            <Route
              path="*"
              element={
                <div className="content-card">
                  <h2>ไม่พบหน้านี้</h2>
                  <Link to="/" className="primary-button">
                    กลับหน้าแรก
                  </Link>
                </div>
              }
            />
          </Routes>
        </main>
        <footer className="page-footer">
          <span>นับง่าย รู้ยอด เก็บออม</span>
          <span>
            THAI COIN COUNTER <span aria-hidden="true">✳</span>
          </span>
        </footer>
      </div>
    </div>
  )
}
export default function App() {
  return (
    <BrowserRouter>
      <Workspace />
    </BrowserRouter>
  )
}
