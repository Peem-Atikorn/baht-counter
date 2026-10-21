"""เรียกโมดูลตามลำดับ preprocess → detect → classify และแปลงพิกัดกลับเป็นภาพต้นฉบับ

พิกัดเหรียญที่ backend เก็บและส่งให้ frontend (รวมถึงพารามิเตอร์ xy ที่รับจากผู้ใช้)
เป็นพิกัดของ**ภาพต้นฉบับ** เสมอ ส่วนโมดูลประมวลผลภาพทำงานบนพิกัดของภาพหลังย่อ
(`pre.resize_factor` คือ ขนาดหลังย่อ/ขนาดต้นฉบับ) ฟังก์ชันในไฟล์นี้เป็นจุดเดียวที่แปลงพิกัด
ไปมาระหว่างสองพิกัดนี้ — ดู docs/backend.md
"""

import logging
import os
import time

import numpy as np

from modules import classification, detection, preprocess
from schemas import Coin, CountResult, PreprocessResult

log = logging.getLogger("pipeline")

STAGES = ("preprocess", "detection", "classification")

# รัศมีเริ่มต้น (พิกเซลของภาพต้นฉบับ) เมื่อผู้ใช้กดเพิ่มเหรียญ และส่วนที่ 2 ยังไม่มี detect_coin_at
DEFAULT_ADD_RADIUS_PX = 40.0


def mock_stages() -> set[str]:
    """COIN_USE_MOCK: "1" = mock ทุกโมดูล (ค่าเริ่มต้น), "0" = ใช้ของจริงทั้งหมด, หรือรายชื่อคั่นด้วย comma"""
    raw = os.getenv("COIN_USE_MOCK", "1").strip()
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


def run(
    image: np.ndarray, anchor: tuple[int, str] | None = None,
) -> tuple[CountResult, dict[str, np.ndarray], dict[str, float]]:
    """คืน (ผล, ภาพกลางทาง, เวลาแต่ละขั้นเป็นวินาที) — app เป็นคนเก็บภาพกลางทางและใส่ URL ลง debug_images"""
    mocks = mock_stages()
    pre_fn, det_fn, cls_fn = _select_fns(mocks)

    h, w = image.shape[:2]
    timings: dict[str, float] = {}
    stage = "preprocess"
    t0 = time.perf_counter()
    try:
        pre = pre_fn(image)
        timings["preprocess"] = time.perf_counter() - t0
        if pre.status == "failed":
            return _failed((w, h), pre.reason or "ภาพนี้ใช้ไม่ได้"), pre.debug_images, timings

        stage = "detection"
        t1 = time.perf_counter()
        coins = det_fn(pre)
        timings["detection"] = time.perf_counter() - t1
        if not coins:
            return _failed((w, h), "ไม่พบเหรียญในภาพ"), pre.debug_images, timings

        stage = "classification"
        t2 = time.perf_counter()
        result = cls_fn(pre, coins, anchor)
        timings["classification"] = time.perf_counter() - t2
    except ValueError:
        if anchor is not None:
            raise  # anchor ไม่ถูกต้อง (coin_id ไม่มี / coin_type ผิด) ให้ route ตอบ 400
        log.exception("pipeline failed at %s", stage)
        return _failed((w, h), "ระบบประมวลผลภาพผิดพลาด กรุณาลองใหม่อีกครั้ง"), {}, timings
    except NotImplementedError:
        log.error("โมดูล %s ยังไม่เสร็จ ตั้ง COIN_USE_MOCK ให้ใช้ mock ของขั้นนี้", stage)
        return _failed((w, h), f"ระบบยังไม่พร้อม: ขั้น {stage} ยังไม่เสร็จ"), {}, timings
    except Exception:
        log.exception("pipeline failed at %s", stage)
        return _failed((w, h), "ระบบประมวลผลภาพผิดพลาด กรุณาลองใหม่อีกครั้ง"), {}, timings
    finally:
        log.info("timings %s mocks=%s", {k: round(v, 3) for k, v in timings.items()}, sorted(mocks))

    f = pre.resize_factor
    result = result.model_copy(update={
        "image_size": (w, h),
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

    classify_coins (รวม mock) ไม่เคยรีเซ็ต status/reason ของเหรียญที่ไม่ใช่ anchor เอง (แค่ไม่เซ็ตให้ใหม่)
    ถ้าไม่ล้างก่อน เหรียญที่เคย needs_confirmation ในรอบก่อนจะค้างสถานะนั้นแม้จำแนกใหม่ได้ชนิดแล้ว
    `source` (ที่มาของเหรียญ ไม่ใช่ผลจำแนก) เก็บไว้เหมือนเดิม
    """
    return c.model_copy(update={
        "color_group": "unknown", "coin_type": None, "value_baht": None,
        "confidence": None, "status": "ok", "reason": None,
    })


def reclassify(image: np.ndarray, coins: list[Coin], anchor: tuple[int, str] | None) -> CountResult:
    """จัดชนิดเหรียญใหม่ทั้งภาพ ใช้ตอนผู้ใช้แก้ชนิดเหรียญ (PUT .../coins/{coin_id})

    `coins` เป็นพิกัดภาพต้นฉบับ (เหมือนที่ส่งให้ frontend) `anchor` คือเหรียญที่ผู้ใช้เลือกชนิดเอง
    """
    _, _, cls_fn = _select_fns(mock_stages())
    pre = _preprocess_original(image)
    if pre.status == "failed":
        return _failed(pre.original_size, pre.reason or "ภาพนี้ใช้ไม่ได้")
    f = pre.resize_factor
    fresh = [_to_resized(_reset_classification(c), f) for c in coins]
    result = cls_fn(pre, fresh, anchor)
    return result.model_copy(update={
        "image_size": pre.original_size,
        "coins": [_to_original(c, f) for c in result.coins],
        "scale_mm_per_px": result.scale_mm_per_px * f if result.scale_mm_per_px is not None else None,
    })


def locate_added_coin(image: np.ndarray, xy: tuple[float, float]) -> Coin | None:
    """หาเหรียญรอบจุดที่ผู้ใช้กด (xy เป็นพิกัดภาพต้นฉบับ) ใช้ตอน POST .../coins

    ใช้ `detection.detect_coin_at(pre, xy)` ของส่วนที่ 2 ถ้ามี (ยังไม่บังคับ ดู AGENTS.md)
    ไม่งั้นวางวงกลมรัศมีค่าเริ่มต้น (`DEFAULT_ADD_RADIUS_PX`) ตรงจุดที่กด คืน None ถ้าปรับปรุงภาพไม่สำเร็จ
    """
    pre = _preprocess_original(image)
    if pre.status == "failed":
        return None
    f = pre.resize_factor
    local_xy = (xy[0] * f, xy[1] * f)
    detect_at = getattr(detection, "detect_coin_at", None)
    coin = detect_at(pre, local_xy) if detect_at else None
    if coin is None:
        coin = Coin(coin_id=0, center_xy=local_xy, radius_px=DEFAULT_ADD_RADIUS_PX * f)
    return _to_original(coin, f)
