# Backend: การเก็บผล, พิกัด, และการแก้ผล (ส่วนที่ 4)

## เก็บข้อมูลที่ไหน

- `BAHT_DATA_DIR` (ค่าเริ่มต้น `storage/`) คือรากของข้อมูลทั้งหมด ไม่หายเมื่อรีสตาร์ท
  (ยกเว้นบน Render แผน Free ที่ไม่มี disk ผูกไว้ ดูหัวข้อ "Env บนเซิร์ฟเวอร์ที่ deploy")
  - `{BAHT_DATA_DIR}/baht.db` — SQLite เก็บผลการนับ (`backend/app/db.py`)
  - `{BAHT_DATA_DIR}/images/{analysis_id}/` — ไฟล์ภาพต้นฉบับ + ภาพกลางทาง (`backend/app/storage.py`)
- ภาพต้นฉบับเก็บเป็น `original<นามสกุลตามชนิดไฟล์ที่อัปโหลด>` (เช่น `.jpg`, `.heic`) ไม่แปลงเป็น PNG
  ภาพกลางทาง (debug images) เก็บเป็น `<ชื่อ>.png` เสมอ (encode จาก numpy ด้วย `cv2.imencode`)
- ไม่เก็บ `PreprocessResult` ข้าม request เพราะมีภาพ numpy ขนาดใหญ่ — ตอนแก้ผล (`PUT`/`POST coins`)
  backend อ่านไฟล์ภาพต้นฉบับจาก storage แล้วรัน preprocess ใหม่ (`pipeline._preprocess_original`)

## พิกัดเหรียญ

- พิกัดที่เก็บใน DB และส่งให้ frontend (`center_xy`, `radius_px`, `ellipse`) เป็นพิกัดของ**ภาพต้นฉบับ**
  (หลังหมุนตาม EXIF แต่ก่อนย่อ) เสมอ — frontend วาด SVG ทับภาพต้นฉบับได้ตรงโดยไม่ต้องแปลงอะไรเอง
- โมดูลประมวลผลภาพ (`preprocess`/`detection`/`classification`) ทำงานบนพิกัดของภาพหลังย่อ
  (`pre.resize_factor` = ขนาดหลังย่อ / ขนาดต้นฉบับ)
- `pipeline.py` เป็นจุดเดียวที่แปลงพิกัดไปมา: `_to_original` (หลังย่อ → ต้นฉบับ, หาร `resize_factor`)
  และ `_to_resized` (ต้นฉบับ → หลังย่อ, คูณ `resize_factor`)
- พารามิเตอร์ `xy` ของ `POST /api/analyses/{id}/coins` (จุดที่ผู้ใช้กดบนภาพ) เป็นพิกัดภาพต้นฉบับเช่นกัน

## กติกาการแก้ผล

| การกระทำ | endpoint | เกิดอะไรขึ้น |
|---|---|---|
| เปลี่ยนชนิดเหรียญ (ปกติ) | `PUT /api/analyses/{id}/coins/{coin_id}` | รัน preprocess ใหม่จากภาพต้นฉบับ แล้วเรียก `classify_coins` ใหม่ทั้งภาพ โดยส่งเหรียญนี้เป็น `anchor=(coin_id, coin_type)` เพื่อคำนวณสเกลใหม่ทั้งภาพ — ชนิดที่ผู้ใช้เลือกชนะเสมอ (`status=ok`, `source=user_edited`) |
| เปลี่ยนชนิดเหรียญ (unknown หรือรัศมีสมมติ) | `PUT /api/analyses/{id}/coins/{coin_id}` | **ไม่** เรียก `classify_coins`/ไม่ใช้เป็น anchor — ตั้งชนิดให้เหรียญนี้เหรียญเดียว (`apply_user_coin`) เพราะ `unknown` ไม่มีขนาดอ้างอิง และเหรียญที่ผู้ใช้เพิ่มเองโดยไม่มี `detect_coin_at` มีรัศมีเป็นค่าสมมติ ใช้คำนวณสเกลเหรียญอื่นไม่ได้ |
| เพิ่มเหรียญที่ระบบมองไม่เห็น | `POST /api/analyses/{id}/coins` | หาวงกลมรอบจุดที่กดด้วย `detection.detect_coin_at` ถ้าส่วนที่ 2 ทำไว้ (ยังไม่บังคับ) ไม่งั้นประมาณรัศมีจากมัธยฐานของเหรียญอื่นในภาพ หรือ `pipeline.FALLBACK_RADIUS_FRACTION` ของด้านสั้นถ้าไม่มีเหรียญอื่น — บันทึก `coin_id` นี้ไว้ในคอลัมน์ `fake_radius_coin_ids` (`db.mark_fake_radius`) เหรียญใหม่ได้ `source=user_added`, `status=needs_confirmation` จนกว่าผู้ใช้จะ `PUT` เลือกชนิด |
| ลบสิ่งที่ไม่ใช่เหรียญ | `DELETE /api/analyses/{id}/coins/{coin_id}` | ลบออกจากรายการแล้วคำนวณยอดรวมใหม่ (ไม่เรียกโมดูลประมวลผลภาพซ้ำ) ถ้าลบจนไม่เหลือเหรียญเลย ผลเป็น `status=failed` (ไม่ใช่ `total_baht=0`) |

เหรียญที่ผู้ใช้ยืนยันชนิดไว้แล้ว (`source != "estimated"` และมี `coin_type`) ต้องไม่ถูกเดาใหม่ทับตอนแก้เหรียญอื่น
ป้องกันสองชั้น: `pipeline._reset_classification` ไม่ล้างเหรียญนี้ก่อนส่งให้ `classify_coins` (ของจริงใช้เป็น
`fixed` คงชนิดไว้) และ `main.lock_user_coins` เขียนค่าที่ผู้ใช้เลือกทับผลที่ได้กลับมาอีกชั้น ไม่พึ่งว่า
`classify_coins` จริงหรือ mock จะเคารพ `source` นี้หรือไม่ (`mock_classify_coins` ของส่วนที่ 3 ยังไม่ทำ)

กฎร่วม: `total_baht` เป็น `None` ทุกครั้งที่มีเหรียญที่ยังระบุชนิด/มูลค่าไม่ได้ (`value_baht is None`)
ห้ามใช้ 0 แทนความหมาย "ไม่มีเหรียญ" หรือ "ยังคำนวณไม่ได้" (ดู AGENTS.md "กติกาโค้ด")

แต่ละครั้งที่แก้ผล (`PUT`/`POST`/`DELETE` coins) จะเพิ่ม `edit_count` ของผลนั้นใน DB ขึ้น 1
ใช้เป็นตัวชี้วัด "จำนวนครั้งที่ผู้ใช้แก้ผล" ใน `GET /api/stats`

## เวลาแต่ละขั้น และสถิติ

`pipeline.run()` คืนเวลา (วินาที) ของแต่ละขั้น (`preprocess`/`detection`/`classification`) เก็บไว้ที่
ผลแต่ละภาพใน DB `GET /api/stats` สรุปเป็นค่าเฉลี่ยของทุกภาพ พร้อมจำนวนครั้งที่แก้ผลรวม/เฉลี่ยต่อภาพ

## ป้ายกำกับจากผลที่ผู้ใช้แก้แล้ว

`GET /api/labels/export` รวมผลทุกภาพที่ `edit_count > 0` เป็น zip เดียว โครงสร้าง:

```text
labels/{analysis_id}.json   # รูปแบบตาม docs/labels.md (พิกัดภาพต้นฉบับอยู่แล้ว ไม่ต้องแปลง)
raw/{analysis_id}{นามสกุล}  # ไฟล์ภาพต้นฉบับ
```

ตั้งชื่อด้วย `analysis_id` (ไม่ใช่ชื่อไฟล์ที่ผู้ใช้อัปโหลด) เพราะกล้องในหน้าเว็บส่งชื่อ `capture.jpg`
ซ้ำกันทุกภาพ — ชื่อเดิมเก็บไว้ที่ `source_filename` ในไฟล์ JSON แทน (ฟิลด์เพิ่มจาก `docs/labels.md`
ของส่วนที่ 1 ที่ผู้รับผิดชอบส่วนที่ 1 ควรรับทราบ) `radius_px` ของเหรียญที่มี `ellipse` ใช้ครึ่งแกนยาว
ตามกติกาภาพเอียงใน `docs/labels.md`

## สลับโมดูลจริง/mock

`COIN_USE_MOCK` (อ่านใน `pipeline.mock_stages()`): `"0"` (ค่าเริ่มต้น) = ของจริงทุกขั้น, `"1"` = mock ทุกขั้น,
หรือรายชื่อคั่นด้วย comma เช่น `"preprocess,classification"` = ขั้นที่ไม่ได้ระบุใช้ของจริง

## Env บนเซิร์ฟเวอร์ที่ deploy

| env | ค่าที่ตั้งบน Render | ความหมาย |
|---|---|---|
| `COIN_USE_MOCK` | `0` | โมดูลจริงครบทั้ง 3 ขั้นแล้ว (preprocess, detection, classification) ใช้ของจริงทั้งหมด |
| `BAHT_DATA_DIR` | `/data` (ตั้งใน `Dockerfile` ไม่ต้องตั้งซ้ำใน dashboard) | แผน Free ของ Render ไม่มี persistent disk ผูกกับ `/data` ข้อมูลจึงยังหายเมื่อ redeploy, restart หรือ sleep แล้วตื่น แม้ path จะคงที่ |
| `PORT` | ไม่ตั้ง (Render ตั้งให้เอง) | อ่านใน `CMD` ของ Dockerfile ผ่าน `${PORT:-8000}` |

**ไม่มีระบบ login:** `GET /api/history` แสดง `analysis_id` ของทุกรายการที่มีในระบบ ไม่ต้องเดา ใครเปิดเว็บก็
ไล่ดูผลและภาพของทุกคนได้ผ่าน `GET /api/analyses/{id}` และภาพทุกภาพ (`/api/analyses/{id}/images/{name}`)
**อย่าใช้ภาพส่วนตัวทดสอบบนเซิร์ฟเวอร์ที่ deploy จริง** ใช้ภาพเหรียญเปล่าๆจาก `data/samples/` พอ

## เทสต์ของ API

ทุก endpoint มี test กรณีปกติ + กรณีล้มเหลวอย่างน้อย 1 อย่าง (เกณฑ์เสร็จ issue #4) ยกเว้นที่ไม่มี input
ให้ผิดได้ (`/api/health`, `/api/coin-types`) ระบุไว้ว่า "ไม่มีกรณีล้มเหลวจาก input" แทนเทสต์ปลอม

| Endpoint | กรณีปกติ | กรณีล้มเหลว |
|---|---|---|
| `GET /api/health` | `test_health` | ไม่มีกรณีล้มเหลวจาก input |
| `GET /api/coin-types` | `test_coin_types` | ไม่มีกรณีล้มเหลวจาก input |
| `POST /api/analyses` | `test_create_and_get_analysis`, `test_create_analysis_with_real_modules_on_sample_image` | `test_rejects_wrong_type` (415), `test_rejects_corrupt_image` (400), `test_rejects_too_large` (413), `test_rejects_too_many_pixels` (413) |
| `GET /api/analyses/{id}` | `test_create_and_get_analysis`, `test_create_analysis_persists_across_fresh_client` | `test_unknown_analysis_404` |
| `GET /api/analyses/{id}/images/{name}` | `test_images_are_served` | `test_images_are_served` (ชื่อภาพไม่มี, 404), `test_image_of_unknown_analysis_404` (analysis ไม่มี, 404) |
| `PUT /api/analyses/{id}/coins/{coin_id}` | `test_update_coin_sets_user_edited_and_recomputes_scale`, `test_update_coin_keeps_previously_edited_coin`, `test_update_coin_to_unknown_does_not_500`, `test_update_coin_to_unknown_after_anchor_still_200` | `test_update_unknown_coin_404`, `test_update_coin_unknown_analysis_404`, `test_update_coin_invalid_coin_type_422` |
| `POST /api/analyses/{id}/coins` | `test_add_coin_needs_confirmation_until_typed`, `test_added_coin_with_fake_radius_is_not_used_as_anchor` | `test_add_coin_unknown_analysis_404`, `test_add_coin_missing_xy_422`, `test_add_coin_non_numeric_xy_422` |
| `DELETE /api/analyses/{id}/coins/{coin_id}` | `test_delete_coin_recomputes_total`, `test_delete_last_coin_leaves_failed_not_zero` | `test_delete_unknown_coin_404` |
| `GET /api/history` | `test_history_lists_newest_first` | `test_history_rejects_invalid_limit` |
| `GET /api/analyses/{id}/export` | `test_export_json_and_csv` | `test_export_unknown_analysis_404`, `test_export_invalid_format_422` |
| `GET /api/labels/export` | `test_labels_export_has_unique_names_and_raw_images` | `test_labels_export_empty_is_404` |
| `GET /api/stats` | `test_stats_reports_edit_count` | `test_stats_before_any_analysis_is_200_not_500` (DB ว่าง ต้องตอบ 200 ค่า 0 ไม่ใช่ 500) |

**พฤติกรรมที่พบแต่ยังไม่แก้ (รอยืนยัน):** `POST /api/analyses/{id}/coins` ด้วย `xy` ที่อยู่นอกภาพ (เช่น
`[99999, 99999]`) ตอบ `201` เฉยๆ ไม่ตรวจพิกัดกับขนาดภาพ ยังไม่ได้เขียนเทสต์หรือแก้โค้ดส่วนนี้
