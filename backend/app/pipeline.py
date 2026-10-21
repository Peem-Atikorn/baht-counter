"""เรียกโมดูลตามลำดับ preprocess → detect → classify และแปลงพิกัดกลับเป็นภาพต้นฉบับ"""

import logging
import os
import time

import numpy as np

from modules import classification, detection, preprocess
from schemas import Coin, CountResult

log = logging.getLogger("pipeline")

STAGES = ("preprocess", "detection", "classification")


def mock_stages() -> set[str]:
    """COIN_USE_MOCK: "1" = mock ทุกโมดูล (ค่าเริ่มต้น), "0" = ใช้ของจริงทั้งหมด, หรือรายชื่อคั่นด้วย comma"""
    raw = os.getenv("COIN_USE_MOCK", "1").strip()
    if raw == "1":
        return set(STAGES)
    if raw in ("", "0"):
        return set()
    return {s.strip() for s in raw.split(",")}


def _failed(size: tuple[int, int], reason: str) -> CountResult:
    return CountResult(
        image_size=size, coins=[], total_baht=None, scale_mm_per_px=None,
        scale_source=None, status="failed", reason=reason,
    )


def _to_original(c: Coin, f: float) -> Coin:
    x, y = c.center_xy
    ellipse = (c.ellipse[0] / f, c.ellipse[1] / f, c.ellipse[2]) if c.ellipse else None
    return c.model_copy(update={"center_xy": (x / f, y / f), "radius_px": c.radius_px / f, "ellipse": ellipse})


def run(image: np.ndarray, anchor: tuple[int, str] | None = None) -> tuple[CountResult, dict[str, np.ndarray]]:
    """คืน (ผล, ภาพกลางทาง) — app เป็นคนเก็บภาพกลางทางและใส่ URL ลง debug_images"""
    mocks = mock_stages()
    pre_fn = preprocess.mock_preprocess if "preprocess" in mocks else preprocess.preprocess
    det_fn = detection.mock_detect_coins if "detection" in mocks else detection.detect_coins
    cls_fn = classification.mock_classify_coins if "classification" in mocks else classification.classify_coins

    h, w = image.shape[:2]
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    try:
        pre = pre_fn(image)
        timings["preprocess"] = time.perf_counter() - t0
        if pre.status == "failed":
            return _failed((w, h), pre.reason or "ภาพนี้ใช้ไม่ได้"), pre.debug_images

        t1 = time.perf_counter()
        coins = det_fn(pre)
        timings["detection"] = time.perf_counter() - t1
        if not coins:
            return _failed((w, h), "ไม่พบเหรียญในภาพ"), pre.debug_images

        t2 = time.perf_counter()
        result = cls_fn(pre, coins, anchor)
        timings["classification"] = time.perf_counter() - t2
    except Exception:
        log.exception("pipeline failed")
        return _failed((w, h), "ระบบประมวลผลภาพผิดพลาด กรุณาลองใหม่อีกครั้ง"), {}
    finally:
        log.info("timings %s mocks=%s", {k: round(v, 3) for k, v in timings.items()}, sorted(mocks))

    f = pre.resize_factor
    result = result.model_copy(update={
        "image_size": (w, h),
        "coins": [_to_original(c, f) for c in result.coins],
        "scale_mm_per_px": result.scale_mm_per_px * f if result.scale_mm_per_px is not None else None,
    })
    return result, pre.debug_images
