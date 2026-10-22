"""ส่วนที่ 4: FastAPI — coin-types, อัปโหลด (รองรับ HEIC), แก้ผล, ประวัติ, export, สถิติ
เก็บผลใน SQLite และภาพใน storage/ ผ่าน db.py / storage.py (ดู docs/backend.md) ไม่หายเมื่อรีสตาร์ท
"""

import io
import json
import logging
import os
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pillow_heif
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from modules.classification import total_baht as calc_total_baht
from modules.preprocess import TARGET_LONG_SIDE
from schemas import (
    COIN_TYPES,
    COIN_TYPES_BY_CODE,
    AnalysisResponse,
    Coin,
    CoinCode,
    CoinCreate,
    CoinTypeInfo,
    CoinUpdate,
    CountResult,
    HealthResponse,
    HistoryItem,
    HistoryPage,
    StatsResponse,
)

from . import db, pipeline, storage

pillow_heif.register_heif_opener()  # ให้ PIL เปิดไฟล์ .heic/.heif จาก iPhone ได้

logging.basicConfig(level=logging.INFO)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 50_000_000  # ไฟล์เล็กแต่ความละเอียดสูงมาก (เช่น PNG สีพื้น) ใช้หน่วยความจำมหาศาลตอนถอดรหัส
# preprocess (ส่วนที่ 1) ย่อเหลือด้านยาว TARGET_LONG_SIDE=1600 อยู่แล้ว ถอดรหัสเกินนี้ไม่ได้ความแม่นเพิ่ม
# เผื่อ 2 เท่าไว้ให้ cv2.resize(INTER_AREA) ของ preprocess มีพิกเซลตั้งต้นพอสมควร (ไม่ย่อจากภาพเล็กเกินไป)
DECODE_LONG_SIDE = 2 * TARGET_LONG_SIDE
ORIENTATION_TAG = 0x0112
EXIF_ORIENTATIONS_THAT_SWAP_WH = {5, 6, 7, 8}
EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}
MEDIA_TYPE_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}
ALLOWED_TYPES = set(EXT_BY_CONTENT_TYPE)

app = FastAPI(title="baht-counter API")


def decode_image(data: bytes) -> tuple[np.ndarray, tuple[int, int]]:
    """อ่านไฟล์ (รวม HEIC) หมุนตาม EXIF orientation แล้วคืน (ภาพ BGR สำหรับประมวลผล, ขนาดภาพต้นฉบับ)

    ถอดรหัสแบบย่อไม่เกิน DECODE_LONG_SIDE แทนเต็มความละเอียด (preprocess ย่อเหลือ TARGET_LONG_SIDE อยู่ดี
    ถอดรหัสเต็มภาพ 20+ ล้านพิกเซลเปลืองหน่วยความจำหลายร้อย MB ต่อ request โดยไม่ได้ความแม่นเพิ่ม — เคยทำให้
    Render ล่ม ดู docs/backend.md) `original_size` คือ (กว้าง, สูง) ของภาพต้นฉบับ**หลังหมุน EXIF** ไม่ใช่ของ
    ภาพที่ถอดรหัสมา ใช้แปลงพิกัดกลับที่จุดเดียวใน pipeline.py (พารามิเตอร์ `original_size` ของ pipeline.run/
    reclassify/locate_added_coin) เพื่อให้พิกัดที่ frontend ได้รับยังเป็นพิกัดภาพต้นฉบับเหมือนเดิมเสมอ
    """
    try:
        img = Image.open(io.BytesIO(data))
        pre_w, pre_h = img.width, img.height  # ขนาดไฟล์ก่อนหมุน EXIF (ใช้ตรวจ MAX_PIXELS และขอ draft())
        if pre_w * pre_h > MAX_PIXELS:
            raise HTTPException(413, "ภาพมีความละเอียดสูงเกินไป กรุณาใช้ภาพไม่เกิน 50 ล้านพิกเซล")

        orientation = img.getexif().get(ORIENTATION_TAG, 1)
        original_size = (
            (pre_h, pre_w) if orientation in EXIF_ORIENTATIONS_THAT_SWAP_WH else (pre_w, pre_h)
        )

        # factor จำนวนเต็ม (ไม่ใช่ 1/2,1/4,1/8 ของ draft โดยตรง) — ปัดขึ้นเสมอเพื่อไม่ให้เกิน DECODE_LONG_SIDE
        # DECODE_LONG_SIDE = 2×TARGET_LONG_SIDE จึงยังไม่หลุดต่ำกว่า TARGET_LONG_SIDE แม้กรณีขอบ (ดูเทสต์)
        long_side = max(pre_w, pre_h)
        factor = max(1, -(-long_side // DECODE_LONG_SIDE))  # ceiling division แบบจำนวนเต็ม
        if img.format == "JPEG" and factor > 1:
            # libjpeg ถอดรหัสแบบย่อ (ได้แค่ 1/2, 1/4, 1/8 เท่านั้น PIL จะเลือกตัวที่ยัง >= ขนาดที่ขอ)
            img.draft("RGB", (pre_w // factor, pre_h // factor))
        img.load()

        if max(img.width, img.height) > DECODE_LONG_SIDE:
            # เกิดได้ 2 กรณี: (1) รูปแบบอื่น (PNG/WebP/HEIC) ไม่มี draft() เลยยังเต็มขนาดอยู่
            # (2) draft ของ JPEG เลือกได้แค่ 1/2,1/4,1/8 ซึ่งหยาบกว่า factor ที่ต้องการ — ย่อซ้ำให้ตรงเป้า
            remaining = max(1, -(-max(img.width, img.height) // DECODE_LONG_SIDE))
            reduced = img.reduce(remaining)
            img.close()
            img = reduced

        transposed = ImageOps.exif_transpose(img)
        img.close()
        rgb = transposed.convert("RGB")
        transposed.close()
    except Image.DecompressionBombError:
        raise HTTPException(413, "ภาพมีความละเอียดสูงเกินไป กรุณาใช้ภาพไม่เกิน 50 ล้านพิกเซล")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "อ่านไฟล์ภาพไม่ได้ กรุณาใช้ไฟล์ JPEG, PNG, WebP หรือ HEIC")

    bgr = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
    return bgr, original_size


def encode_png(img: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def encode_display_jpeg(image: np.ndarray) -> bytes:
    """ภาพสำหรับเว็บจากพิกัดต้นฉบับหลังหมุน EXIF แล้ว ไม่ใช้ภาพย่อของ pipeline"""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise HTTPException(500, "สร้างภาพสำหรับแสดงผลไม่สำเร็จ")
    return buf.tobytes()


def format_server_timing(timings_sec: dict[str, float]) -> str:
    """Server-Timing header ตามมาตรฐาน (หน่วย ms) ขั้นที่ไม่มีคีย์ใน timings_sec จะไม่ถูกใส่ (ไม่ใช่ 0)
    ดูได้ใน DevTools ของเบราว์เซอร์ → Network → เลือก request → แท็บ Timing (ดู docs/backend.md)
    """
    return ", ".join(f"{stage};dur={seconds * 1000:.1f}" for stage, seconds in timings_sec.items())


def get_or_404(analysis_id: str) -> dict:
    record = db.get_analysis(analysis_id)
    if record is None:
        raise HTTPException(404, "ไม่พบผลการนับนี้")
    return record


def load_original(record: dict) -> tuple[np.ndarray, tuple[int, int]]:
    data = storage.load_image(record["id"], f"original{record['original_ext']}")
    if data is None:  # ไม่ควรเกิดถ้า storage/ ไม่ถูกลบนอกระบบ
        raise HTTPException(404, "ไม่พบภาพต้นฉบับของผลการนับนี้")
    return decode_image(data)


def recompute_overall(coins: list[Coin], prior_reason: str | None) -> tuple[float | None, str, str | None]:
    """ยอดรวม + status + reason ของทั้งภาพ จากรายการเหรียญปัจจุบัน (ใช้หลังแก้/เพิ่ม/ลบเหรียญ)"""
    if not coins:
        return None, "failed", "ไม่พบเหรียญในภาพ"
    total = calc_total_baht(coins)
    needs = any(c.status == "needs_confirmation" for c in coins)
    status = "needs_confirmation" if needs else "ok"
    return total, status, (prior_reason if needs else None)


def apply_user_coin(coin: Coin, coin_type: CoinCode) -> Coin:
    """ตั้งชนิดให้เหรียญเดียว โดยไม่เรียก classify_coins ซ้ำ (ไม่ใช้เป็น anchor คำนวณสเกลทั้งภาพ)

    ใช้เมื่อ `coin_type` เป็น `unknown` หรือเหรียญนี้รัศมีเป็นค่าสมมติ (ผู้ใช้เพิ่มเองโดยไม่มี `detect_coin_at`)
    เพราะขนาดของเหรียญนี้ไม่น่าเชื่อถือพอจะใช้อนุมานสเกลของเหรียญอื่นทั้งภาพ (ดู docs/backend.md)
    """
    spec = COIN_TYPES_BY_CODE.get(coin_type)
    return coin.model_copy(update={
        "coin_type": coin_type,
        "value_baht": spec.value_baht if spec else None,
        "color_group": spec.color_group if spec else coin.color_group,
        "confidence": None,
        "source": "user_edited",
        "status": "ok",
        "reason": None if spec else "ไม่ใช่เหรียญไทย ลบเหรียญนี้ออกเพื่อให้รวมยอดได้",
    })


def lock_user_coins(
    original_coins: list[Coin], edited_id: int, edited: Coin, result: CountResult,
) -> CountResult:
    """เหรียญที่ผู้ใช้ยืนยันชนิดไว้แล้ว (ตอนนี้หรือก่อนหน้า) ต้องไม่เปลี่ยนจาก classify_coins รอบใหม่

    ไม่พึ่งว่า classify_coins จริงหรือ mock จะเคารพ `source`/`coin_type` ที่ส่งเข้าไปหรือไม่
    (`pipeline._reset_classification` พยายามไม่ล้างค่านี้อยู่แล้ว แต่ backend ยืนยันซ้ำที่นี่เป็นชั้นที่สอง)
    """
    locked = {
        c.coin_id: c for c in original_coins
        if c.coin_id != edited_id and c.source != "estimated" and c.coin_type is not None
    }
    locked[edited_id] = edited
    coins = [locked.get(c.coin_id, c) for c in result.coins]
    total, status, reason = recompute_overall(coins, result.reason)
    return result.model_copy(update={"coins": coins, "total_baht": total, "status": status, "reason": reason})


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/api/coin-types", response_model=list[CoinTypeInfo])
def coin_types():
    return COIN_TYPES


# def ธรรมดา (ไม่ใช่ async) FastAPI จะรันใน threadpool งานประมวลผลภาพจึงไม่บล็อก request อื่น
@app.post("/api/analyses", response_model=AnalysisResponse, status_code=201)
def create_analysis(file: UploadFile, response: Response):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "รองรับเฉพาะไฟล์ JPEG, PNG, WebP หรือ HEIC")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "ไฟล์ใหญ่เกิน 15 MB")

    t_decode = time.perf_counter()
    image, original_size = decode_image(data)
    decode_sec = time.perf_counter() - t_decode
    result, debug, timings = pipeline.run(image, original_size=original_size)

    t_save = time.perf_counter()
    analysis_id = uuid.uuid4().hex
    ext = EXT_BY_CONTENT_TYPE[file.content_type]
    storage.save_image(analysis_id, f"original{ext}", data)
    if ext in (".heic", ".heif"):
        storage.save_image(analysis_id, "display.jpg", encode_display_jpeg(image))
    for name, img in debug.items():
        storage.save_image(analysis_id, f"{name}.png", encode_png(img))

    result = result.model_copy(update={
        "debug_images": {name: f"/api/analyses/{analysis_id}/images/{name}" for name in debug},
    })
    db.insert_analysis(analysis_id, result, timings, file.filename, ext)
    save_sec = time.perf_counter() - t_save

    # Server-Timing: เวลาแต่ละขั้นจริงของ request นี้ ไม่ปนกับผลเก่าหรือ request อื่น (ดู docs/backend.md)
    # decode มาก่อน preprocess เสมอ (ลำดับที่ทำงานจริงใน create_analysis)
    response.headers["Server-Timing"] = format_server_timing({"decode": decode_sec, **timings, "save": save_sec})
    return AnalysisResponse(analysis_id=analysis_id, result=result)


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str):
    record = get_or_404(analysis_id)
    return AnalysisResponse(analysis_id=analysis_id, result=record["result"])


@app.get("/api/analyses/{analysis_id}/images/{name}")
def get_image(analysis_id: str, name: str):
    record = get_or_404(analysis_id)
    if name == "original" and record["original_ext"] in (".heic", ".heif"):
        data = storage.load_image(analysis_id, "display.jpg")
        if data is None:
            # ผลเก่าก่อนเพิ่ม display.jpg ต้องเปิดจากประวัติได้ด้วย
            image, _ = load_original(record)
            data = encode_display_jpeg(image)
            storage.save_image(analysis_id, "display.jpg", data)
        return Response(data, media_type="image/jpeg")
    filename = f"original{record['original_ext']}" if name == "original" else f"{name}.png"
    data = storage.load_image(analysis_id, filename)
    if data is None:
        raise HTTPException(404, "ไม่พบภาพนี้")
    media = MEDIA_TYPE_BY_EXT.get(Path(filename).suffix.lower(), "application/octet-stream")
    return Response(data, media_type=media)


@app.put("/api/analyses/{analysis_id}/coins/{coin_id}", response_model=AnalysisResponse)
def update_coin(analysis_id: str, coin_id: int, body: CoinUpdate):
    record = get_or_404(analysis_id)
    coins = record["result"].coins
    target = next((c for c in coins if c.coin_id == coin_id), None)
    if target is None:
        raise HTTPException(404, "ไม่พบเหรียญนี้")

    # ใช้เป็น anchor (คำนวณสเกลทั้งภาพใหม่) เฉพาะเหรียญไทยที่ขนาดเชื่อถือได้ — ไม่ใช่ unknown
    # และไม่ใช่เหรียญที่ผู้ใช้เพิ่มเองด้วยรัศมีสมมติ (ดู pipeline.locate_added_coin, docs/backend.md)
    use_as_anchor = body.coin_type != "unknown" and coin_id not in record["fake_radius_coin_ids"]
    if use_as_anchor:
        image, original_size = load_original(record)
        try:
            result = pipeline.reclassify(image, coins, anchor=(coin_id, body.coin_type), original_size=original_size)
        except ValueError as exc:
            raise HTTPException(400, f"เลือกชนิดเหรียญนี้ไม่ได้: {exc}")
        edited = next(c for c in result.coins if c.coin_id == coin_id).model_copy(
            update={"source": "user_edited", "status": "ok", "reason": None},
        )
    else:
        result = record["result"]
        edited = apply_user_coin(target, body.coin_type)

    result = lock_user_coins(coins, coin_id, edited, result)
    db.update_result(analysis_id, result)
    return AnalysisResponse(analysis_id=analysis_id, result=result)


@app.post("/api/analyses/{analysis_id}/coins", response_model=AnalysisResponse, status_code=201)
def add_coin(analysis_id: str, body: CoinCreate):
    record = get_or_404(analysis_id)
    coins = record["result"].coins

    w, h = record["result"].image_size
    x, y = body.xy
    if not (0 <= x < w and 0 <= y < h):
        raise HTTPException(422, "พิกัดอยู่นอกภาพ")

    image, original_size = load_original(record)
    located = pipeline.locate_added_coin(image, body.xy, coins, original_size=original_size)
    if located is None:
        raise HTTPException(422, "ปรับปรุงภาพไม่สำเร็จ เพิ่มเหรียญไม่ได้")
    new_coin, is_fake_radius = located

    new_id = max((c.coin_id for c in coins), default=-1) + 1
    new_coin = new_coin.model_copy(update={
        "coin_id": new_id,
        "source": "user_added",
        "status": "needs_confirmation",
        "reason": "ผู้ใช้เพิ่มเหรียญนี้ กรุณาเลือกชนิด",
    })
    coins = [*coins, new_coin]
    total, status, reason = recompute_overall(
        coins, "กดเลือกชนิดของเหรียญที่มีเครื่องหมาย ? เพื่อให้ระบบคำนวณที่เหลือ",
    )
    result = record["result"].model_copy(
        update={"coins": coins, "total_baht": total, "status": status, "reason": reason},
    )
    db.update_result(analysis_id, result)
    if is_fake_radius:
        db.mark_fake_radius(analysis_id, new_id)
    return AnalysisResponse(analysis_id=analysis_id, result=result)


@app.delete("/api/analyses/{analysis_id}/coins/{coin_id}", response_model=AnalysisResponse)
def delete_coin(analysis_id: str, coin_id: int):
    record = get_or_404(analysis_id)
    coins = record["result"].coins
    if not any(c.coin_id == coin_id for c in coins):
        raise HTTPException(404, "ไม่พบเหรียญนี้")

    coins = [c for c in coins if c.coin_id != coin_id]
    total, status, reason = recompute_overall(coins, record["result"].reason)
    result = record["result"].model_copy(
        update={"coins": coins, "total_baht": total, "status": status, "reason": reason},
    )
    db.update_result(analysis_id, result)
    return AnalysisResponse(analysis_id=analysis_id, result=result)


@app.get("/api/history", response_model=HistoryPage)
def history(limit: int = 20, offset: int = 0):
    if not (1 <= limit <= 100):
        raise HTTPException(422, "limit ต้องอยู่ระหว่าง 1 ถึง 100")
    if offset < 0:
        raise HTTPException(422, "offset ต้องไม่ติดลบ")
    records, total = db.list_history(limit, offset)
    items = [
        HistoryItem(
            analysis_id=r["id"],
            created_at=r["created_at"],
            status=r["result"].status,
            total_baht=r["result"].total_baht,
            coin_count=len(r["result"].coins),
        )
        for r in records
    ]
    return HistoryPage(items=items, total=total)


@app.get("/api/analyses/{analysis_id}/export")
def export_analysis(analysis_id: str, format: Literal["json", "csv"] = "json"):
    record = get_or_404(analysis_id)
    result = record["result"]

    if format == "json":
        body = AnalysisResponse(analysis_id=analysis_id, result=result).model_dump_json(indent=2)
        return Response(
            body, media_type="application/json",
            headers={"content-disposition": f'attachment; filename="{analysis_id}.json"'},
        )

    lines = ["coin_id,coin_type,value_baht,color_group,source,status,center_x,center_y,radius_px"]
    for c in result.coins:
        value = "" if c.value_baht is None else c.value_baht
        lines.append(
            f"{c.coin_id},{c.coin_type or ''},{value},{c.color_group},{c.source},{c.status},"
            f"{c.center_xy[0]:.1f},{c.center_xy[1]:.1f},{c.radius_px:.1f}",
        )
    return Response(
        "\n".join(lines) + "\n", media_type="text/csv",
        headers={"content-disposition": f'attachment; filename="{analysis_id}.csv"'},
    )


@app.get("/api/labels/export")
def export_labels():
    """รวมผลที่ผู้ใช้แก้แล้วทั้งหมดเป็นไฟล์ป้ายกำกับ + ภาพต้นฉบับทีละภาพ (รูปแบบตาม docs/labels.md) ใน zip เดียว

    ตั้งชื่อไฟล์ด้วย analysis_id (ไม่ใช่ชื่อไฟล์ที่ผู้ใช้อัปโหลด) เพราะกล้องในหน้าเว็บส่งชื่อ `capture.jpg`
    ซ้ำกันทุกภาพ ชื่อเดิมเก็บไว้ที่ `source_filename` แทน (ฟิลด์เพิ่มจาก docs/labels.md ของส่วนที่ 1)
    """
    records = db.all_edited()
    if not records:
        raise HTTPException(404, "ยังไม่มีผลที่ผู้ใช้แก้แล้ว")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in records:
            result = r["result"]
            image_name = f"{r['id']}{r['original_ext']}"
            label = {
                "image": image_name,
                "source_filename": r["original_filename"],
                "image_size": list(result.image_size),
                "coins": [
                    {
                        "center_xy": list(c.center_xy),
                        "radius_px": round((c.ellipse[0] / 2) if c.ellipse else c.radius_px, 1),
                        "coin_type": c.coin_type,
                    }
                    for c in result.coins
                    if c.coin_type is not None
                ],
                "notes": "",
            }
            zf.writestr(f"labels/{r['id']}.json", json.dumps(label, ensure_ascii=False, indent=2))
            original = storage.load_image(r["id"], f"original{r['original_ext']}")
            if original is not None:
                zf.writestr(f"raw/{image_name}", original)
    return Response(
        buf.getvalue(), media_type="application/zip",
        headers={"content-disposition": 'attachment; filename="labels.zip"'},
    )


@app.get("/api/stats", response_model=StatsResponse)
def get_stats():
    return StatsResponse(**db.stats())


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """เสิร์ฟหน้าเว็บที่ build แล้ว (frontend/dist) ใช้ตอนรันใน Docker (ดู Dockerfile)

    กัน path traversal: เสิร์ฟไฟล์จริงได้เฉพาะเมื่อ path ที่ resolve แล้วยังอยู่ใต้ `dist` เท่านั้น
    ไม่งั้นส่ง index.html (ให้ React Router จัดการ) path ที่ขึ้นต้น `api/` ยังคืน 404 ตามเดิม
    """
    dist = dist.resolve()
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "ไม่พบ endpoint นี้")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


# ไม่ mount ตอนรัน pytest/dev เพราะไดเรกทอรีนี้ไม่มี จึง endpoint /api/* ด้านบนไม่ถูกบัง
_FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", "/app/frontend_dist"))
if _FRONTEND_DIST.is_dir():
    mount_frontend(app, _FRONTEND_DIST)
