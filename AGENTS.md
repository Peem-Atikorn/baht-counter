# คำแนะนำสำหรับ AI coding assistant

ไฟล์นี้สำหรับ AI ที่ช่วยสมาชิกทีมเขียนโค้ดใน repo นี้ อ่านให้จบก่อนเริ่มงาน

## โปรเจกต์นี้คืออะไร

`baht-counter` เว็บแอปนับเหรียญไทยจากภาพถ่ายและรวมยอดเงิน โครงงานวิชาการประมวลผลภาพและเสียง ทีม 5 คน แบ่งงานเป็น 5 ส่วน

- ภาพรวม โครงสร้างโฟลเดอร์ และขั้นตอน git: `README.md`
- แผนฉบับเต็ม (schema, สัญญาของโมดูล, API, เกณฑ์เสร็จ): `docs/plan.md`

**เป้าหลักของวิชาคือเทคนิคประมวลผลภาพ** ให้ใช้ OpenCV / NumPy / scikit-image ทำทีละขั้นที่อธิบายได้ (threshold, morphology, Hough, watershed, HSV ฯลฯ) อย่าแทนทั้งไปป์ไลน์ด้วยโมเดลสำเร็จรูป CNN ใช้ได้เฉพาะเป็นวิธีเปรียบเทียบในส่วนที่ 3

## เริ่ม session ทุกครั้ง

1. ถามผู้ใช้ว่าทำ**ส่วนที่เท่าไร** และ **branch ชื่ออะไร** (รูปแบบ `pX/Name`) ถ้ายังไม่รู้
2. ดู branch ปัจจุบันด้วย `git branch --show-current`
   - ถ้าอยู่บน `develop` หรือ `main` ห้ามแก้โค้ด ให้สลับไป branch ของผู้ใช้ก่อน หรือสร้างใหม่จาก `develop`
3. ดึงงานล่าสุด: `git switch develop && git pull && git switch pX/Name && git merge develop`
4. อ่านงานของส่วนนั้น:
   - issue: `gh issue view X` (ส่วนที่ X = issue #X) หรือ https://github.com/Peem-Atikorn/baht-counter/issues/X
   - หัวข้อ "ส่วนที่ X" ในหัวข้อ 4 ของ `docs/plan.md` และหัวข้อ 3 (ข้อตกลงร่วม)
5. เลือกงานถัดไปจาก checklist ใน issue ที่ยังไม่ได้ทำ แล้วบอกผู้ใช้ก่อนเริ่ม

### ตารางรายสัปดาห์คือลำดับงาน ไม่ใช่ข้อจำกัดเวลา

ตาราง "แผนรายสัปดาห์" ใน `docs/plan.md` หัวข้อ 5 บอกว่างานไหนต้องเสร็จก่อนงานไหน และเป็นกำหนดส่งช้าสุด
- ถ้างานที่ต้องเสร็จก่อนเสร็จแล้ว ทำข้อถัดไปใน checklist ได้ทันที ไม่ต้องรอให้ถึงสัปดาห์นั้น
- อย่าเลื่อนงานด้วยเหตุผลว่า "เป็นงานสัปดาห์ X" ถ้าทำได้แล้วให้ทำ
- งานที่รอได้จริงคืองานที่ต้องใช้ผลจากที่อื่นที่ยังไม่มี เช่น ปรับความแม่นต้องรอชุดข้อมูลที่มีป้ายกำกับ, ทดสอบกล้องบนมือถือต้องรอ deploy HTTPS ให้บอกผู้ใช้ว่ารออะไร แล้วใช้ `mock_*()` หรือ `data/samples/` ทำส่วนที่ทำได้ไปก่อน
- กฎที่ยังใช้เสมอไม่ว่าทำเร็วแค่ไหน: หลังล็อกชุดทดสอบ ห้ามปรับระบบโดยดูผลจากชุดทดสอบ และแก้ schema กลางต้องผ่าน PR ที่ทุกคนเห็น

## ใครเป็นเจ้าของโฟลเดอร์ไหน

| ส่วน | Issue | โฟลเดอร์ |
|---|---|---|
| 1 ข้อมูลและปรับปรุงภาพ | #1 | `backend/modules/preprocess/`, `data/` |
| 2 หาตำแหน่งเหรียญ | #2 | `backend/modules/detection/` |
| 3 จำแนกชนิดและประเมินผล | #3 | `backend/modules/classification/`, `eval/` |
| 4 Backend และ Deploy | #4 | `backend/app/`, `backend/schemas/`, `docker-compose.yml`, `.github/workflows/` |
| 5 Frontend | #5 | `frontend/` |

- แก้เฉพาะโฟลเดอร์ของส่วนตัวเอง ถ้าจำเป็นต้องแตะของส่วนอื่น ให้บอกผู้ใช้ก่อน
- `backend/schemas/` คือสัญญากลางของทุกส่วน แก้ได้แต่ต้องเพิ่ม `schema_version` และบอกผู้ใช้ให้แจ้งทั้งทีมใน PR
- เทสต์ของแต่ละส่วนอยู่ใน `backend/tests/` ตั้งชื่อไฟล์ตามโมดูล เช่น `test_detection.py`

## กติกาโค้ด

- โมดูลประมวลผลภาพเป็นฟังก์ชัน Python บริสุทธิ์ รับ object เข้า คืน object ออก ไม่อ่าน/เขียนไฟล์หรือฐานข้อมูลเอง
- ทุกโมดูลมี `mock_*()` ที่คืนผลตัวอย่างตาม schema เพื่อให้ส่วนอื่นใช้ได้ก่อนโมดูลจริงเสร็จ
- สัญญาของโมดูล (ดู `docs/plan.md` หัวข้อ 3.4):
  - ส่วนที่ 1: `preprocess(image) -> PreprocessResult`
  - ส่วนที่ 2: `detect_coins(pre: PreprocessResult) -> list[Coin]`
  - ส่วนที่ 3: `classify_coins(pre, coins, anchor=None) -> CountResult`
- ค่าที่ประเมินไม่ได้เป็น `None`/`null` คู่กับ `status` และ `reason` **ห้ามใช้ 0 แทน**
  - `status`: `ok` / `needs_confirmation` / `failed`
  - `source` ของชนิดเหรียญ: `estimated` / `user_edited` / `user_added`
- ใส่หน่วยในชื่อฟิลด์: `diameter_px`, `diameter_mm`, `value_baht`, `scale_mm_per_px`
- รหัสเหรียญ: `THB_0_25`, `THB_0_50`, `THB_1`, `THB_2`, `THB_5`, `THB_10`, `unknown`
- ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย (เช่น "ภาพเบลอ กรุณาถือกล้องให้นิ่ง")
- Python 3.11, FastAPI + Pydantic / React + Vite + TypeScript + Tailwind (ตาม README)
- ภาพทดสอบที่ใช้ใน test ให้ใช้จาก `data/samples/` อย่า commit ภาพใหญ่หรือ `data/raw/`

## Git และ PR

- ทำงานบน branch `pX/Name` ของผู้ใช้เท่านั้น push ตรงเข้า `develop` หรือ `main` ไม่ได้ (branch ถูกป้องกันไว้)
- ห้าม `git push --force`, `git reset --hard` บน branch ที่แชร์กัน หรือแก้ประวัติ commit โดยไม่ถามผู้ใช้
- commit message และชื่อ PR ขึ้นต้นด้วยเลขส่วนแล้วตามด้วยเนื้องาน เช่น `p2: เพิ่ม watershed แยกเหรียญที่ชิดกัน` ไม่ตั้งชื่อตามสัปดาห์
- **ไม่ต้องใส่ `Co-Authored-By` ของ AI หรือบรรทัด "Generated with ..." ใน commit และ PR**
- เปิด PR เข้า `develop` เสมอ (ไม่ใช่ `main`) และเขียน `Refs #X` หรือ `Closes #X` เมื่องานของส่วนนั้นเสร็จทั้งหมด
  ```bash
  gh pr create --base develop --title "p2: ..." --body "Refs #2"
  ```
- commit หรือเปิด PR เมื่อผู้ใช้สั่งเท่านั้น
- เมื่อทำงานใน checklist ของ issue เสร็จ ให้บอกผู้ใช้ไปติ๊กใน issue

## คำสั่งรันและเทสต์

รายละเอียดการติดตั้งอยู่ใน `README.md` หัวข้อ "การติดตั้งและรัน"

- Backend เทสต์: `cd backend && .venv/Scripts/python -m pytest` (macOS/Linux: `.venv/bin/python`)
- Backend รัน: `.venv/Scripts/python -m uvicorn app.main:app --reload` (พอร์ต 8000)
- Frontend: `cd frontend && npm run build` (ตรวจ type + build), `npm run dev` (พอร์ต 5173), `npx oxlint src`
- โมดูลจริงที่ยังไม่เสร็จ `raise NotImplementedError` pipeline ใช้ `mock_*()` แทนตาม env `COIN_USE_MOCK` (ดู `backend/app/pipeline.py`)
- แก้ schema ใน `backend/schemas/` แล้วต้องรัน `npm run gen:api` (ขณะ backend รันอยู่) และ commit `frontend/src/api/schema.d.ts` ด้วย
- `docker compose up` ยังไม่มี (ส่วนที่ 4)
