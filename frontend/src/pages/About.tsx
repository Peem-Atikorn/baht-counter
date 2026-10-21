import { Link } from 'react-router-dom'
import Icon from '../components/Icon'
export default function About() {
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
      <Link to="/count" className="primary-button">
        พร้อมแล้ว เริ่มนับเหรียญ <Icon name="arrow" />
      </Link>
    </article>
  )
}
