import { Link } from 'react-router-dom'
import CoinArt from '../components/CoinArt'
import Icon from '../components/Icon'

const coins = [
  { value: '25', unit: 'สต.', name: '25 สตางค์', detail: 'ทองแดง · 16 มม.', color: 'copper' },
  { value: '50', unit: 'สต.', name: '50 สตางค์', detail: 'ทองแดง · 18 มม.', color: 'copper' },
  { value: '1', unit: 'บาท', name: '1 บาท', detail: 'สีเงิน · 20 มม.', color: 'silver' },
  { value: '2', unit: 'บาท', name: '2 บาท', detail: 'สีทอง · 21.75 มม.', color: 'gold' },
  { value: '5', unit: 'บาท', name: '5 บาท', detail: 'สีเงิน · 24 มม.', color: 'silver' },
  { value: '10', unit: 'บาท', name: '10 บาท', detail: 'สองสี · 26 มม.', color: 'bimetal' },
]
export default function Home() {
  return <div className="dashboard-grid"><div className="dashboard-main">
    <section className="hero-card"><div className="hero-visual"><span className="hero-label"><span /> เก็บเล็ก ผสมน้อย</span><CoinArt /><span className="art-caption">small coins, big possibilities.</span></div><div className="hero-content"><div><p className="eyebrow">MAKE EVERY BAHT COUNT</p><h2>เปลี่ยนกองเหรียญ<br />ให้เป็นยอดเงิน</h2><p>แค่ถ่ายรูป ก็รู้ว่าเหรียญตรงหน้ามีมูลค่าเท่าไร</p></div><Link to="/count" className="hero-cta" aria-label="เริ่มนับเหรียญ"><Icon name="arrow" /></Link></div></section>
    <section className="start-section" aria-labelledby="start-heading"><div className="section-heading"><h2 id="start-heading">วันนี้ เริ่มนับกันเลย</h2><span>ง่าย ๆ ในรูปเดียว</span></div><div className="action-grid"><Link to="/count?source=camera" className="action-card camera-card"><span className="action-illustration"><Icon name="camera" /><span className="tiny-spark">+</span></span><div><h3>ถ่ายรูปเหรียญ</h3><p>เปิดกล้อง แล้วเริ่มนับ</p></div><Icon name="arrow" /></Link><Link to="/count?source=upload" className="action-card upload-card"><span className="action-illustration"><Icon name="upload" /><span className="tiny-spark">+</span></span><div><h3>อัปโหลดรูป</h3><p>เลือกรูปที่มีอยู่ในเครื่อง</p></div><Icon name="arrow" /></Link></div></section>
    <section className="how-section" aria-labelledby="how-heading"><div className="section-heading"><h2 id="how-heading">จากภาพ สู่ยอดเงิน</h2><Link to="/about">ดูวิธีใช้งาน <Icon name="arrow" /></Link></div><ol className="steps"><li><span>01</span><div><h3>วางเหรียญ</h3><p>พื้นเรียบ เห็นครบทุกเหรียญ</p></div></li><li><span>02</span><div><h3>ถ่ายหรืออัปโหลด</h3><p>ถ่ายจากด้านบน แสงพอดี</p></div></li><li><span>03</span><div><h3>ดูผลการนับ</h3><p>ตรวจชนิดและยอดเงินรวม</p></div></li></ol></section>
  </div><aside className="info-panel"><div className="welcome"><div className="welcome-icon"><span>฿</span><i /></div><div><p>สวัสดี, นักเก็บออม</p><span>มาให้ค่าทุกเหรียญกัน</span></div></div><section className="coin-guide"><div className="section-heading"><h2>เหรียญที่นับได้</h2><span className="count-pill">6 ชนิด</span></div><p className="section-description">รู้จักเหรียญไทยในกระเป๋าของคุณ</p><ul>{coins.map(c => <li key={c.name}><span className={`coin-token ${c.color}`} aria-hidden="true"><strong>{c.value}</strong><small>{c.unit}</small></span><div><h3>{c.name}</h3><p>{c.detail}</p></div><Icon name="check" /></li>)}</ul></section><section className="tip-card"><span className="tip-icon"><Icon name="sun" /></span><p className="eyebrow">A LITTLE TIP</p><h2>แสงดี นับได้ง่ายขึ้น</h2><p>วางเหรียญบนพื้นสีเรียบ หลีกเลี่ยงเงาและแสงสะท้อน เพื่อให้เห็นขอบเหรียญชัดเจน</p><Link to="/about">เตรียมรูปให้พร้อม <Icon name="arrow" /></Link></section></aside></div>
}
