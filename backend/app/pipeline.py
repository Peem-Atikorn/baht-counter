"""เรียกโมดูลตามลำดับ preprocess → detect → classify และแปลงพิกัดกลับเป็นภาพต้นฉบับ

พิกัดเหรียญที่ backend เก็บและส่งให้ frontend (รวมถึงพารามิเตอร์ xy ที่รับจากผู้ใช้)
เป็นพิกัดของ**ภาพต้นฉบับ** เสมอ ส่วนโมดูลประมวลผลภาพทำงานบนพิกัดของภาพหลังย่อ
(`pre.resize_factor` คือ ขนาดหลังย่อ/ขนาดต้นฉบับ) ฟังก์ชันในไฟล์นี้เป็นจุดเดียวที่แปลงพิกัด
ไปมาระหว่างสองพิกัดนี้ — ดู docs/backend.md
"""

import logging
import os
import statistics
import time

import numpy as np

from modules import classification, detection, preprocess
from schemas import Coin, CountResult, PreprocessResult

log = logging.getLogger("pipeline")

STAGES = ("preprocess", "detection", "classification")

# เมื่อไม่มีเหรียญอื่นในภาพให้ประมาณรัศมี (ตอนผู้ใช้เพิ่มเหรียญแรกโดยไม่มี detect_coin_at)
FALLBACK_RADIUS_FRACTION = 0.03  # ของด้านสั้นของภาพ


def mock_stages() -> set[str]:
    """COIN_USE_MOCK: "0" = ใช้ของจริงทั้งหมด (ค่าเริ่มต้น), "1" = mock ทุกโมดูล, หรือรายชื่อคั่นด้วย comma"""
    raw = os.getenv("COIN_USE_MOCK", "0").strip()
    if raw == "1":
        return set(STAGES)
    if raw in ("", "0"):
        return set()
    names = {s.strip() for s in raw.split(",") if s.strip()}
    unknown = names - set(STAGES)
    if unknown:
        raise ValueError(f"COIN_USE_MOCK มีชื่อที่ไม่รู้จัก {sorted(unknown)} ใช้ได้เฉพาะ {list(STAGES)}")
    return names


def _select_fns(mocks: set[str]):
    pre_fn = preprocess.mock_preprocess if "preprocess" in mocks else preprocess.preprocess
    det_fn = detection.mock_detect_coins if "detection" in mocks else detection.detect_coins
    cls_fn = classification.mock_classify_coins if "classification" in mocks else classification.classify_coins
    return pre_fn, det_fn, cls_fn


def _failed(size: tuple[int, int], reason: str) -> CountResult:
    return CountResult(
        image_size=size, coins=[], total_baht=None, scale_mm_per_px=None,
        scale_source=None, status="failed", reason=reason,
    )


def _to_original(c: Coin, f: float) -> Coin:
    x, y = c.center_xy
    ellipse = (c.ellipse[0] / f, c.ellipse[1] / f, c.ellipse[2]) if c.ellipse else None
    return c.model_copy(update={"center_xy": (x / f, y / f), "radius_px": c.radius_px / f, "ellipse": ellipse})


def _to_resized(c: Coin, f: float) -> Coin:
    x, y = c.center_xy
    ellipse = (c.ellipse[0] * f, c.ellipse[1] * f, c.ellipse[2]) if c.ellipse else None
    return c.model_copy(update={"center_xy": (x * f, y * f), "radius_px": c.radius_px * f, "ellipse": ellipse})


def _decode_factor(decoded_width: int, original_size: tuple[int, int] | None) -> float:
    """ตัวคูณจากภาพต้นฉบับจริง -> ภาพที่ `image` เป็น (ขนาดที่ main.decode_image ถอดรหัสมา)

    `original_size` เป็น `None` หมายถึง `image` ที่ส่งเข้ามาคือภาพต้นฉบับเอง (ตัวคูณ = 1.0 พฤติกรรมเดิมก่อน
    main.decode_image ย่อตอนถอดรหัส — เทสต์เดิมที่เรียก pipeline ตรงด้วยภาพต้นฉบับไม่ต้องแก้) ไม่ใช่ `None`
    หมายถึง main.py ถอดรหัสแบบย่อมาแล้ว ต้องคูณเข้ากับ `pre.resize_factor` ก่อนแปลงพิกัดกลับเป็นภาพต้นฉบับจริง
    (ดู main.decode_image, docs/backend.md)
    """
    if original_size is None:
        return 1.0
    original_w = original_size[0]
    return decoded_width / original_w if original_w else 1.0


def run(
    image: np.ndarray, anchor: tuple[int, str] | None = None,
    original_size: tuple[int, int] | None = None,
) -> tuple[CountResult, dict[str, np.ndarray], dict[str, float]]:
    """คืน (ผล, ภาพกลางทาง, เวลาแต่ละขั้นเป็นวินาที) — app เป็นคนเก็บภาพกลางทางและใส่ URL ลง debug_images

    `original_size` (กว้าง, สูง) ของภาพต้นฉบับจริง ถ้า `image` ถูกย่อตอนถอดรหัสมาก่อน (ดู main.decode_image)
    `None` = `image` คือภาพต้นฉบับเอง — ผลลัพธ์ (`image_size`, พิกัดเหรียญ) เป็นพิกัดภาพต้นฉบับเสมอไม่ว่ากรณีใด
    """
    mocks = mock_stages()
    pre_fn, det_fn, cls_fn = _select_fns(mocks)

    h, w = image.shape[:2]
    orig_wh = original_size if original_size is not None else (w, h)
    decode_factor = _decode_factor(w, original_size)
    timings: dict[str, float] = {}
    stage = "preprocess"
    t0 = time.perf_counter()
    try:
        pre = pre_fn(image)
        timings["preprocess"] = time.perf_counter() - t0
        if pre.status == "failed":
            return _failed(orig_wh, pre.reason or "ภาพนี้ใช้ไม่ได้"), pre.debug_images, timings

        stage = "detection"
        t1 = time.perf_counter()
        coins = det_fn(pre)
        timings["detection"] = time.perf_counter() - t1
        if not coins:
            return _failed(orig_wh, "ไม่พบเหรียญในภาพ"), pre.debug_images, timings

        stage = "classification"
        t2 = time.perf_counter()
        result = cls_fn(pre, coins, anchor)
        timings["classification"] = time.perf_counter() - t2
    except ValueError:
        if anchor is not None:
            raise  # anchor ไม่ถูกต้อง (coin_id ไม่มี / coin_type ผิด) ให้ route ตอบ 400
        log.exception("pipeline failed at %s", stage)
        return _failed(orig_wh, "ระบบประมวลผลภาพผิดพลาด กรุณาลองใหม่อีกครั้ง"), {}, timings
    except NotImplementedError:
        log.error("โมดูล %s ยังไม่เสร็จ ตั้ง COIN_USE_MOCK ให้ใช้ mock ของขั้นนี้", stage)
        return _failed(orig_wh, f"ระบบยังไม่พร้อม: ขั้น {stage} ยังไม่เสร็จ"), {}, timings
    except Exception:
        log.exception("pipeline failed at %s", stage)
        return _failed(orig_wh, "ระบบประมวลผลภาพผิดพลาด กรุณาลองใหม่อีกครั้ง"), {}, timings
    finally:
        log.info("timings %s mocks=%s", {k: round(v, 3) for k, v in timings.items()}, sorted(mocks))

    f = pre.resize_factor * decode_factor
    result = result.model_copy(update={
        "image_size": orig_wh,
        "coins": [_to_original(c, f) for c in result.coins],
        "scale_mm_per_px": result.scale_mm_per_px * f if result.scale_mm_per_px is not None else None,
    })
    return result, pre.debug_images, timings


def _preprocess_original(image: np.ndarray) -> PreprocessResult:
    """รัน preprocess ใหม่จากภาพต้นฉบับ ใช้เมื่อผู้ใช้แก้ผล — backend ไม่เก็บ PreprocessResult ข้าม request
    เพราะมีภาพ numpy ขนาดใหญ่ ให้รันซ้ำแทน (ภาพเดียวเร็วพอสำหรับงานแก้ไขแบบโต้ตอบ)"""
    pre_fn, _, _ = _select_fns(mock_stages())
    return pre_fn(image)


def _reset_classification(c: Coin) -> Coin:
    """ล้างผลจำแนกเดิมก่อนส่งให้ classify_coins ใหม่ เหมือนเหรียญที่เพิ่งมาจาก detect_coins

    ยกเว้นเหรียญที่ผู้ใช้ยืนยันชนิดไว้แล้ว (`source != "estimated"` และมี `coin_type`) — ไม่ล้าง
    classify_coins จริงใช้ `source`/`coin_type` นี้เป็นข้อจำกัด (`fixed`) คงชนิดนั้นไว้แทนเดาใหม่
    ถ้าล้างไปด้วย เหรียญที่ผู้ใช้เลือกไว้ก่อนจะถูกเดาใหม่ทับ (ชนิดที่ผู้ใช้เลือกหายไป)

    ของเหรียญที่ยังล้าง: classify_coins (รวม mock) ไม่เคยรีเซ็ต status/reason เอง (แค่ไม่เซ็ตให้ใหม่)
    ถ้าไม่ล้างก่อน เหรียญที่เคย needs_confirmation ในรอบก่อนจะค้างสถานะนั้นแม้จำแนกใหม่ได้ชนิดแล้ว
    """
    if c.source != "estimated" and c.coin_type is not None:
        return c
    return c.model_copy(update={
        "color_group": "unknown", "coin_type": None, "value_baht": None,
        "confidence": None, "status": "ok", "reason": None,
    })


def reclassify(
    image: np.ndarray, coins: list[Coin], anchor: tuple[int, str] | None,
    original_size: tuple[int, int] | None = None,
) -> CountResult:
    """จัดชนิดเหรียญใหม่ทั้งภาพ ใช้ตอนผู้ใช้แก้ชนิดเหรียญ (PUT .../coins/{coin_id})

    `coins` เป็นพิกัดภาพต้นฉบับ (เหมือนที่ส่งให้ frontend) `anchor` คือเหรียญที่ผู้ใช้เลือกชนิดเอง `original_size`
    ดู `run()` — `None` = `image` คือภาพต้นฉบับเอง ไม่ใช่ `None` = `image` ถูกย่อตอนถอดรหัสมา (main.decode_image)
    """
    _, _, cls_fn = _select_fns(mock_stages())
    pre = _preprocess_original(image)
    h, w = image.shape[:2]
    orig_wh = original_size if original_size is not None else (w, h)
    if pre.status == "failed":
        return _failed(orig_wh, pre.reason or "ภาพนี้ใช้ไม่ได้")
    f = pre.resize_factor * _decode_factor(w, original_size)
    fresh = [_to_resized(_reset_classification(c), f) for c in coins]
    result = cls_fn(pre, fresh, anchor)
    return result.model_copy(update={
        "image_size": orig_wh,
        "coins": [_to_original(c, f) for c in result.coins],
        "scale_mm_per_px": result.scale_mm_per_px * f if result.scale_mm_per_px is not None else None,
    })


def locate_added_coin(
    image: np.ndarray, xy: tuple[float, float], existing_coins: list[Coin],
    original_size: tuple[int, int] | None = None,
) -> tuple[Coin, bool] | None:
    """หาเหรียญรอบจุดที่ผู้ใช้กด (xy เป็นพิกัดภาพต้นฉบับ) ใช้ตอน POST .../coins

    ใช้ `detection.detect_coin_at(pre, xy)` ของส่วนที่ 2 ถ้ามี (ยังไม่บังคับ ดู AGENTS.md) ไม่งั้นประมาณรัศมี
    จากมัธยฐานของเหรียญอื่นในภาพ หรือ `FALLBACK_RADIUS_FRACTION` ของด้านสั้นถ้าไม่มีเหรียญอื่นให้เทียบ

    คืน `(เหรียญ, เป็นรัศมีสมมติหรือไม่)` หรือ `None` ถ้าปรับปรุงภาพไม่สำเร็จ รัศมีสมมติ (`True`)
    ห้ามใช้เป็น anchor คำนวณสเกลทั้งภาพ เพราะไม่ใช่ขนาดจริงของเหรียญ (ดู main.py / docs/backend.md)
    `original_size` ดู `run()` — `None` = `image`/`xy` คือพิกัดภาพต้นฉบับเองอยู่แล้ว
    """
    pre = _preprocess_original(image)
    if pre.status == "failed":
        return None
    w = image.shape[1]
    f = pre.resize_factor * _decode_factor(w, original_size)
    local_xy = (xy[0] * f, xy[1] * f)
    detect_at = getattr(detection, "detect_coin_at", None)
    coin = detect_at(pre, local_xy) if detect_at else None
    if coin is not None:
        return _to_original(coin, f), False

    radii = [c.radius_px * f for c in existing_coins]
    if radii:
        radius = statistics.median(radii)
    else:
        h, w = pre.image.shape[:2]
        radius = FALLBACK_RADIUS_FRACTION * min(h, w)
    coin = Coin(coin_id=0, center_xy=local_xy, radius_px=radius)
    return _to_original(coin, f), True
