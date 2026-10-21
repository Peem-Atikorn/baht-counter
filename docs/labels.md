# รูปแบบป้ายกำกับ

หนึ่งภาพ = หนึ่งไฟล์ `data/labels/<ชื่อภาพไม่มีนามสกุล>.json` พิกัดเป็นพิกเซลของ**ภาพต้นฉบับหลังหมุนตาม EXIF** (ยังไม่ย่อ)

```json
{
  "image": "p1_white_room_top_001.jpg",
  "image_size": [4032, 3024],
  "coins": [
    {"center_xy": [1203.5, 880.0], "radius_px": 142.0, "coin_type": "THB_10"},
    {"center_xy": [1650.0, 910.5], "radius_px": 108.0, "coin_type": "THB_1"}
  ],
  "notes": ""
}
```

- `coin_type` ใช้รหัสเดียวกับ schema กลาง (`THB_0_25` … `THB_10`, `unknown`)
- เหรียญที่ซ้อนจนเห็นไม่ถึงครึ่ง: ไม่ต้องใส่ และเขียนใน `notes`
- ภาพเอียง: ใส่ `radius_px` เป็นครึ่งหนึ่งของแกนยาว

## `data/splits.csv`

```csv
image,split
p1_white_room_top_001.jpg,tune
p2_wood_window_tilt15_004.jpg,test
web_001.jpg,web
```

`split` ∈ `tune` (ชุดปรับระบบ) / `test` (ชุดทดสอบ, ล็อกสัปดาห์ 3) / `web` (ชุดภาพเว็บ)
