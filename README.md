# baht-counter

เว็บแอปนับเหรียญและคำนวณยอดเงินไทยจากภาพถ่าย โครงงานวิชาการประมวลผลภาพและเสียง (ทีม 5 คน, 5 สัปดาห์)

ผู้ใช้ถ่ายหรืออัปโหลดภาพเหรียญที่วางบนพื้นราบ ระบบหาเหรียญทุกเหรียญ บอกชนิด และรวมยอดเงิน ถ้าระบบอ่านผิด ผู้ใช้แก้บนหน้าเว็บได้

แผนงานฉบับเต็มอยู่ที่ [`docs/plan.md`](docs/plan.md)

---

## ระบบทำอะไร

รองรับเหรียญไทยที่ใช้อยู่ปัจจุบัน 6 ชนิด

| ชนิด | รหัส | เส้นผ่านศูนย์กลาง (มม.) | กลุ่มสี |
|---|---|---|---|
| 25 สตางค์ | `THB_0_25` | 16 | copper |
| 50 สตางค์ | `THB_0_50` | 18 | copper |
| 1 บาท | `THB_1` | 20 | silver |
| 2 บาท | `THB_2` | 21.75 | gold |
| 5 บาท | `THB_5` | 24 | silver |
| 10 บาท | `THB_10` | 26 | bimetal |

**แนวคิดหลัก:** ภาพจากเว็บไม่มีไม้บรรทัด ระบบจึงใช้**สีแบ่งกลุ่มก่อน แล้วใช้ขนาดเทียบกันเอง** เพื่อหาสเกล (มม./พิกเซล) ที่ทำให้ทุกเหรียญตรงกับชนิดที่เป็นไปได้มากที่สุด ถ้าสเกลไม่ชัด ระบบตอบ `needs_confirmation` แล้วให้ผู้ใช้เลือกชนิดเหรียญ 1 เหรียญเป็นตัวอ้างอิง

```mermaid
flowchart LR
    A[ภาพเข้า] --> B[ปรับปรุงภาพ<br/>ส่วนที่ 1]
    B --> C[หาเหรียญ<br/>ส่วนที่ 2]
    C --> D[จัดกลุ่มสี + หาสเกลและชนิด<br/>ส่วนที่ 3]
    D --> E[ยอดเงินรวม]
```

## เทคโนโลยี

| ชั้น | เทคโนโลยี |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind CSS |
| Backend | Python 3.11 + FastAPI + Pydantic |
| ประมวลผลภาพ | OpenCV, NumPy, scikit-image (CNN เปรียบเทียบด้วย PyTorch) |
| ฐานข้อมูล | SQLite |
| Deploy | Docker Compose บนเซิร์ฟเวอร์ที่มี HTTPS |

## โครงสร้างโปรเจกต์

```text
baht-counter/
├── frontend/                 # ส่วนที่ 5
├── backend/
│   ├── app/                  # ส่วนที่ 4: FastAPI, routes, DB
│   │   └── pipeline.py       # เรียกโมดูลตามลำดับ
│   ├── modules/
│   │   ├── preprocess/       # ส่วนที่ 1
│   │   ├── detection/        # ส่วนที่ 2
│   │   └── classification/   # ส่วนที่ 3
│   ├── schemas/              # Pydantic schema กลาง (แก้ต้องผ่าน PR ที่ทุกคนเห็น)
│   └── tests/
├── data/
│   ├── samples/              # 5–10 ภาพตัวอย่างที่ทุกคนรันได้ (เก็บใน git)
│   ├── raw/                  # ภาพทั้งหมด (ไม่เก็บใน git)
│   ├── labels/               # ป้ายกำกับ JSON
│   └── splits.csv
├── eval/                     # สคริปต์ประเมินผล
├── docs/
└── docker-compose.yml
```

## การแบ่งงาน

| ส่วน | งาน | Issue | Prefix ของ branch |
|---|---|---|---|
| 1 | ชุดข้อมูล การปรับปรุงภาพ และการตรวจคุณภาพภาพ | [#1](https://github.com/Peem-Atikorn/baht-counter/issues/1) | `p1/` |
| 2 | หาตำแหน่งเหรียญ | [#2](https://github.com/Peem-Atikorn/baht-counter/issues/2) | `p2/` |
| 3 | จำแนกชนิดเหรียญ หาสเกล และการประเมินผลรวม | [#3](https://github.com/Peem-Atikorn/baht-counter/issues/3) | `p3/` |
| 4 | Backend API ฐานข้อมูล และ Deploy | [#4](https://github.com/Peem-Atikorn/baht-counter/issues/4) | `p4/` |
| 5 | Frontend เว็บแอป | [#5](https://github.com/Peem-Atikorn/baht-counter/issues/5) | `p5/` |

ผู้รับผิดชอบแต่ละส่วนกด Assign ตัวเองใน issue ของส่วนนั้น

## การทำงานร่วมกัน

### Branch

```text
pX/<ชื่องาน>  ──PR──▶  develop  ──PR (1 approve)──▶  main
```

| Branch | ใช้ทำอะไร | กฎ |
|---|---|---|
| `main` | เวอร์ชันที่ deploy และส่งอาจารย์ | รับเฉพาะ PR จาก `develop`, ต้องมี 1 คน approve |
| `develop` | รวมงานทุกส่วน (default branch) | ต้องเปิด PR, merge เองได้ |
| `pX/<ชื่องาน>` | งานของส่วนที่ X | สร้างจาก `develop` |
| `docs/<ชื่องาน>` | เอกสารหรือของที่ใช้ร่วมกันทุกส่วน | สร้างจาก `develop` |

**ตั้งชื่อ branch**
- ขึ้นต้นด้วยเลขส่วนของตัวเอง `p1/` ถึง `p5/` ส่วนที่ตามหลังตั้งเองได้
- ใช้ภาษาอังกฤษตัวเล็ก คั่นคำด้วย `-` เช่น `p1/clahe`, `p2/watershed`, `p3/scale-search`, `p4/docker`, `p5/camera`
- 1 branch ต่อ 1 งานย่อย merge แล้วลบทิ้ง

### ขั้นตอน

```bash
git switch develop
git pull
git switch -c p2/watershed
# ... แก้โค้ด, commit ...
git push -u origin p2/watershed
```

จากนั้นเปิด PR เข้า `develop` บน GitHub และเขียนอ้าง issue ในคำอธิบาย PR
- `Refs #2` สำหรับงานย่อยระหว่างทาง
- `Closes #2` เมื่องานของส่วนนั้นเสร็จทั้งหมด

### ข้อตกลง

- โมดูลประมวลผลภาพเป็นฟังก์ชัน Python บริสุทธิ์ และมี `mock_*()` คืนผลตัวอย่างตาม schema
- ค่าที่ประเมินไม่ได้เป็น `null` + `status` + `reason` ห้ามใช้ 0 แทน
- หน่วยอยู่ในชื่อฟิลด์ เช่น `diameter_px`, `value_baht`, `scale_mm_per_px`
- แก้ schema กลางต้องเปิด PR ที่ทุกคนเห็น และเพิ่ม `schema_version`

## การติดตั้งและรัน

_ยังไม่มี ส่วนที่ 4 จะเติมเมื่อมี `docker-compose.yml`_ (เป้าหมาย: `docker compose up` คำสั่งเดียว)
