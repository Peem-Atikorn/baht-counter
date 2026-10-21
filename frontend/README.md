# Baht Counter Frontend

React + Vite + TypeScript + Tailwind CSS บน branch `p5/paphawit`

## เริ่มใช้งาน

ใช้ Node.js 22.12+ หรือรุ่นที่ Vite รองรับ แล้วรันใน `frontend/`:

```powershell
npm ci
npm run dev
```

เปิด http://localhost:5173 โดย Vite จะส่ง `/api` ไป backend ที่พอร์ต 8000

ทดลองหน้าจอโดยไม่รัน backend (ผลการนับเป็นข้อมูลจำลอง):

```powershell
$env:VITE_USE_MOCK='1'
npm run dev
```

เอาตัวแปรออกด้วย `Remove-Item Env:VITE_USE_MOCK` ก่อนเริ่ม dev server ใหม่เมื่อต้องการใช้ backend

ตรวจโค้ด: `npm run build` และ `npm run lint`

## หน้าที่มี

- `/`: แดชบอร์ดสีครีม/ส้มอิฐ การ์ดเริ่มนับ และข้อมูลเหรียญ 6 ชนิด
- `/count`: กล้อง อัปโหลด ลากวาง วางภาพจากคลิปบอร์ด และพรีวิว
- `/result/:id`: ภาพ ยอดรวม ตาราง และสถานะจาก API
- `/about`: วิธีเตรียมภาพและคำอธิบายขั้นตอนระบบ

มือถือใช้เมนูด้านล่าง เดสก์ท็อปใช้เมนูด้านซ้าย ภาพประกอบเป็น SVG ในโปรเจกต์
ฟอนต์โหลดจาก Google Fonts และมี system font สำรอง

โค้ดตั้งต้นนำมาจาก Frontend ใน PR #15 เท่านั้น ยังไม่รวม backend ของ PR นั้น
การประมวลผลภาพจริง ประวัติ และ API แก้ผลยังขึ้นกับงานส่วนอื่น โหมดทดลองแสดงผลจำลอง ไม่ได้วิเคราะห์ภาพที่อัปโหลด
