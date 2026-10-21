"""วิธีพื้นฐานสำหรับเปรียบเทียบในรายงาน

สมมติว่าถ่ายจากความสูงเดิมทุกครั้ง จึงใช้สเกลคงที่ค่าเดียว (เท่ากับช่วงรัศมีพิกเซลคงที่ต่อชนิด)
และเลือกชนิดที่ขนาดใกล้ที่สุดจากทั้ง 6 ชนิด ไม่ใช้สี
"""
from __future__ import annotations

import numpy as np

from schemas import Coin, CountResult, PreprocessResult

from .classify import diameter_px, summarize
from .coin_specs import COIN_SPECS


def fit_baseline_scale(diameters_px: list[float], coin_types: list[str]) -> float:
    """หาสเกลคงที่จากชุดปรับระบบ (ค่ามัธยฐานของ ขนาดจริง / ขนาดพิกเซล)"""
    ratios = [COIN_SPECS[t].diameter_mm / d for d, t in zip(diameters_px, coin_types)
              if t in COIN_SPECS and d > 0]
    if not ratios:
        raise ValueError("ไม่มีเหรียญที่มีป้ายกำกับสำหรับหาสเกลของวิธีพื้นฐาน")
    return float(np.median(ratios))


def radius_ranges_px(mm_per_px: float) -> dict[str, tuple[float, float]]:
    """ช่วงรัศมีพิกเซลของแต่ละชนิด (ขอบเขตอยู่กึ่งกลางระหว่างชนิดที่ขนาดติดกัน) สำหรับใส่ในรายงาน"""
    specs = sorted(COIN_SPECS.values(), key=lambda s: s.diameter_mm)
    radii = [s.diameter_mm / 2 / mm_per_px for s in specs]
    bounds = [0.0] + [(a + b) / 2 for a, b in zip(radii, radii[1:])] + [float("inf")]
    return {s.code: (bounds[k], bounds[k + 1]) for k, s in enumerate(specs)}


def classify_coins_baseline(pre: PreprocessResult, coins: list[Coin], mm_per_px: float) -> CountResult:
    out = []
    for c in coins:
        size_mm = diameter_px(c) * mm_per_px
        t = min(COIN_SPECS, key=lambda k: abs(size_mm - COIN_SPECS[k].diameter_mm))
        out.append(c.model_copy(update=dict(
            coin_type=t, value_baht=COIN_SPECS[t].value_baht, confidence=None,
            status="ok", reason=None,
        )))
    return summarize(pre, out, mm_per_px, "inferred")
