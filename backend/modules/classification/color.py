"""จัดกลุ่มสีของเหรียญ (W5 HSV)

วัดสีสองบริเวณต่อเหรียญ: ใจกลาง (inner) และวงแหวนใกล้ขอบ (ring)
เพราะ 10 บาทมีใจกลางสีทองแต่ขอบสีเงิน ตัดพิกเซลแสงสะท้อนและเงามืดออกก่อน
แล้วใช้ค่ามัธยฐานแทนค่าเฉลี่ยเพื่อทนต่อพิกเซลผิดปกติ
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from schemas import Coin

# รัศมีบริเวณที่วัด เทียบกับรัศมีเหรียญ (เลี่ยงขอบที่ปนพื้นหลังและเงา)
INNER_R = 0.50
RING_R = (0.72, 0.90)

# พิกเซลที่ไม่ใช้วัดสี (สเกล OpenCV: H 0-179, S/V 0-255)
GLARE_V_MIN = 235      # สว่างจัด และ
GLARE_S_MAX = 40       # แทบไม่มีสี = แสงสะท้อน
DARK_V_MAX = 40        # มืดจัด = เงาหรือร่องลาย
MIN_PIXELS = 15

# เกณฑ์แบ่งสี ปรับด้วยชุด tune (eval/run_eval.py --split tune --dump-colors, วงกลมจากป้ายกำกับ 474 เหรียญ)
# - เหรียญเงินใต้ไฟห้องสีอุ่นอมเหลือง S มัธยฐาน 60 p95 ≈ 110 ส่วนทองแดง S p5 ≈ 115, 2 บาท S p5 ≈ 98
#   เงินมีมากกว่า 2 บาทมาก (237 vs 16) จึงตั้งเกณฑ์ให้เงินเกือบทั้งหมดผ่าน 2 บาทที่ S ต่ำจะถูกมองเป็นเงิน
# - ทองแดง H p95 ≈ 18–19 ทอง/10 บาท H p5 ≈ 20–21
# ชุด tune กลุ่มสีถูก 57% -> 93% (เงิน 92%, ทองแดง 95%, 2 บาท 75%, สองสี 100%)
SILVER_S_MAX = 110     # ความอิ่มสีต่ำกว่านี้ = เงิน
COPPER_H_MAX = 18      # H <= 18 หรือ >= 170 = ทองแดง (ส้มแดง)
GOLD_H_MAX = 35        # 18 < H <= 35 = ทอง (เหลือง)
# 10 บาท: ใจกลาง S / ขอบ S ชุด tune p5 = 1.48 เหรียญสีเดียวทุกชนิด p95 <= 1.10
# ใช้อัตราส่วนแทนเกณฑ์ silver ของขอบ เพราะแสงอุ่นทำให้ขอบเงินของ 10 บาทอิ่มสีเกินเกณฑ์ (เดิม 10 บาทถูกแค่ 46%)
# ไม่ต่ำกว่า 1.4 เพราะ 2 บาทที่ขอบซีดเพราะแสงสะท้อนได้ราว 1.3 (test_pale_gold_ring_is_not_bimetal)
BIMETAL_S_RATIO = 1.4


@dataclass
class ColorFeatures:
    inner_hsv: tuple[float, float, float] | None
    ring_hsv: tuple[float, float, float] | None
    inner_label: str
    ring_label: str
    group: str


def _ring_mask(d2: np.ndarray, r_in: float, r_out: float) -> np.ndarray:
    return (d2 >= r_in ** 2) & (d2 <= r_out ** 2)


def _median_hsv(hsv: np.ndarray, mask: np.ndarray) -> tuple[float, float, float] | None:
    px = hsv[mask]
    if len(px) == 0:
        return None
    h, s, v = px[:, 0].astype(int), px[:, 1].astype(int), px[:, 2].astype(int)
    keep = ~((v >= GLARE_V_MIN) & (s <= GLARE_S_MAX)) & (v > DARK_V_MAX)
    if keep.sum() < MIN_PIXELS:
        return None
    h, s, v = h[keep], s[keep], v[keep]
    # hue วนรอบ (179 ติดกับ 0) เลื่อนสีแดงไปอยู่ฝั่งลบก่อนหามัธยฐาน
    h = np.where(h >= 150, h - 180, h)
    return float(np.median(h)) % 180, float(np.median(s)), float(np.median(v))


def label_hsv(hsv: tuple[float, float, float] | None) -> str:
    if hsv is None:
        return "unknown"
    h, s, _ = hsv
    if s < SILVER_S_MAX:
        return "silver"
    if h <= COPPER_H_MAX or h >= 170:
        return "copper"
    if h <= GOLD_H_MAX:
        return "gold"
    return "unknown"


def _bimetal_by_ratio(inner, ring) -> bool:
    """ใจกลางอิ่มสีกว่าขอบชัดเจนและใจกลางเป็นโทนทอง = 10 บาท แม้แสงอุ่นทำให้ขอบไม่ผ่านเกณฑ์ silver"""
    if inner is None or ring is None:
        return False
    h, s, _ = inner
    return COPPER_H_MAX < h <= GOLD_H_MAX and s >= BIMETAL_S_RATIO * max(ring[1], 1.0)


def coin_color_features(hsv_image: np.ndarray, coin: Coin) -> ColorFeatures:
    # ภาพเอียงทำให้เหรียญเป็นวงรี ใช้วงกลมรัศมีครึ่งแกนสั้นซึ่งอยู่ในเหรียญเสมอ
    r = coin.radius_px
    if coin.ellipse is not None:
        r = min(r, coin.ellipse[1] / 2)
    # ตัดเฉพาะกรอบรอบเหรียญ ไม่ต้องคำนวณทั้งภาพ
    cx, cy = coin.center_xy
    h, w = hsv_image.shape[:2]
    x0, x1 = max(int(cx - r) - 1, 0), min(int(cx + r) + 2, w)
    y0, y1 = max(int(cy - r) - 1, 0), min(int(cy + r) + 2, h)
    crop = hsv_image[y0:y1, x0:x1]
    yy, xx = np.ogrid[y0:y1, x0:x1]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2

    inner = _median_hsv(crop, _ring_mask(d2, 0, INNER_R * r))
    ring = _median_hsv(crop, _ring_mask(d2, RING_R[0] * r, RING_R[1] * r))
    inner_label, ring_label = label_hsv(inner), label_hsv(ring)

    # สองสีเฉพาะเมื่อขอบเป็นสีเงินจริง ขอบ 2 บาทที่ซีดเพราะแสงสะท้อนยังเป็นสีทอง
    if inner_label == "gold" and ring_label == "silver" or _bimetal_by_ratio(inner, ring):
        group = "bimetal"
    elif inner_label == ring_label or ring_label == "unknown":
        group = inner_label
    elif inner_label == "unknown":
        group = ring_label
    else:
        # สองบริเวณไม่ตรงกัน ใช้สีของทั้งเหรียญตัดสิน
        whole = _median_hsv(crop, _ring_mask(d2, 0, RING_R[1] * r))
        group = label_hsv(whole)
    return ColorFeatures(inner, ring, inner_label, ring_label, group)


def color_groups(image_bgr: np.ndarray, coins: list[Coin]) -> list[ColorFeatures]:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    return [coin_color_features(hsv, c) for c in coins]
