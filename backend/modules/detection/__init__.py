"""ส่วนที่ 2: หาตำแหน่งเหรียญ (Coin Detection)

ไปป์ไลน์หลัก:
PreprocessResult -> Thresholding -> Morphology -> Distance Transform -> Watershed -> Fit Ellipse -> list[Coin]
"""

from __future__ import annotations

import cv2
import numpy as np

from modules.detection.baselines import (
    detect_coins_hough,
    detect_coins_kmeans,
    detect_coins_no_watershed,
)
from modules.detection.debug import (
    render_detection_overlay,
    render_distance_map,
    render_watershed_map,
)
from modules.detection.fit import extract_coins_from_markers
from modules.detection.segment import clean_morphology, segment_coins, segment_coins_otsu
from modules.detection.watershed import apply_watershed
from schemas import COIN_TYPES, Coin, PreprocessResult


def detect_coins(pre: PreprocessResult) -> list[Coin]:
    """ค้นหาเหรียญทั้งหมดในภาพ คืน list[Coin] ที่มี center_xy, radius_px, ellipse

    ใช้เทคนิค:
    1. Multi-cue Segmentation: ผสาน Grayscale Otsu และ Color Difference จากพื้นหลัง
    2. Morphological Closing (เติมรูในเหรียญและแสงสะท้อน) + Opening (ตัด noise)
    3. Distance Transform + Local Maxima Peak Finding เพื่อสร้าง Seeds
    4. Component-Guided Watershed Segmentation ตัดแบ่งเหรียญที่วางสัมผัส/ชิดกัน
    5. Fit Ellipse ต่อเหรียญ โดยใช้แกนยาว (Major Axis) รองรับภาพถ่ายมุมเอียง
    6. บันทึกภาพกลางทางลง pre.debug_images สำหรับหน้า 'เกี่ยวกับ'
    """
    gray = pre.gray
    image = pre.image

    # 1. Canny edge สำหรับภาพ debug
    edges = cv2.Canny(gray, 40, 120)

    # 2. Binarization & Morphology
    raw_mask = segment_coins(image, gray)
    clean_mask = clean_morphology(raw_mask)

    # 3. Watershed Segmentation
    markers, dist = apply_watershed(image, clean_mask)

    # 4. สกัดข้อมูลเหรียญและ Fit Ellipse
    coins = extract_coins_from_markers(markers, clean_mask=clean_mask)

    # 5. สร้างภาพกลางทาง (Debug Images)
    if pre.debug_images is not None:
        pre.debug_images["detection_edges"] = edges
        pre.debug_images["detection_mask"] = clean_mask
        pre.debug_images["detection_distance"] = render_distance_map(dist)
        pre.debug_images["detection_watershed"] = render_watershed_map(markers)
        pre.debug_images["detection_result"] = render_detection_overlay(image, coins)

    return coins


def detect_coin_at(pre: PreprocessResult, xy: tuple[float, float]) -> Coin | None:
    """ค้นหาเหรียญรอบจุดที่ผู้ใช้กด (xy เป็นพิกัดภาพหลัง preprocess)

    ใช้เมื่อผู้ใช้กดบนภาพเพื่อเพิ่มเหรียญที่ระบบตรวจจับไม่พบ:
    1. ตรวจสอบก่อนว่าจุดนี้อยู่ในขอบเขตของเหรียญที่ตรวจพบอยู่แล้วหรือไม่
    2. หากไม่อยู่ ทำการ Crop บริเวณรอบพิกัด (ROI) แล้วค้นหาขอบเขตเหรียญเฉพาะจุด
    """
    x, y = xy
    h, w = pre.gray.shape[:2]

    # ตรวจสอบว่าพิกัดอยู่ในขอบเขตภาพหรือไม่
    if not (0 <= x < w and 0 <= y < h):
        return None

    # 1. ตรวจสอบกับเหรียญที่ตรวจจับได้ในรอบปกติก่อน
    all_coins = detect_coins(pre)
    for c in all_coins:
        cx, cy = c.center_xy
        dist_sq = (cx - x) ** 2 + (cy - y) ** 2
        # หากจุดที่กดอยู่ภายในรัศมีของเหรียญเดิม (เผื่อ 15%)
        if dist_sq <= (c.radius_px * 1.15) ** 2:
            return c

    # 2. Localized Search: Crop บริเวณรอบจุดที่กดขนาด 200x200 px
    roi_radius = 120
    x1, y1 = max(0, int(x - roi_radius)), max(0, int(y - roi_radius))
    x2, y2 = min(w, int(x + roi_radius)), min(h, int(y + roi_radius))
    if x2 - x1 < 20 or y2 - y1 < 20:
        return None

    local_gray = pre.gray[y1:y2, x1:x2]
    local_mask = segment_coins_otsu(local_gray)
    local_mask = clean_morphology(local_mask)

    contours, _ = cv2.findContours(local_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    local_click = (x - x1, y - y1)

    best_coin: Coin | None = None
    min_dist_to_center = float("inf")

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 80:
            continue

        # ตรวจสอบว่าจุดที่คลิกอยู่ภายใน contour หรือไม่
        dist_to_contour = cv2.pointPolygonTest(cnt, local_click, True)
        if dist_to_contour >= -10:  # อยู่ข้างใน หรือห่างไม่เกิน 10 px
            if len(cnt) >= 5:
                (lcx, lcy), (d1, d2), angle = cv2.fitEllipse(cnt)
                major = max(d1, d2)
                minor = min(d1, d2)
                r = major / 2.0
                ellipse = (float(major), float(minor), float(angle))
            else:
                (lcx, lcy), r = cv2.minEnclosingCircle(cnt)
                ellipse = None

            gcx, gcy = lcx + x1, lcy + y1
            d_center = np.hypot(gcx - x, gcy - y)
            if d_center < min_dist_to_center:
                min_dist_to_center = d_center
                best_coin = Coin(
                    coin_id=0,
                    center_xy=(float(gcx), float(gcy)),
                    radius_px=float(r),
                    ellipse=ellipse,
                    source="user_added",
                    status="ok",
                )

    if best_coin is not None:
        return best_coin

    # 3. ลอง Hough Circles ใน ROI สำหรับกรณีขอบเลือนลาง
    blurred = cv2.GaussianBlur(local_gray, (7, 7), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=20,
        param1=50,
        param2=25,
        minRadius=15,
        maxRadius=roi_radius,
    )
    if circles is not None:
        for cx_l, cy_l, r_l in circles[0]:
            gcx, gcy = cx_l + x1, cy_l + y1
            if np.hypot(gcx - x, gcy - y) <= r_l * 1.1:
                return Coin(
                    coin_id=0,
                    center_xy=(float(gcx), float(gcy)),
                    radius_px=float(r_l),
                    ellipse=None,
                    source="user_added",
                    status="ok",
                )

    return None


def mock_detect_coins(pre: PreprocessResult) -> list[Coin]:
    """วางเหรียญทุกชนิดเรียงเป็นแถวกลางภาพ รัศมีเป็นสัดส่วนกับขนาดจริง"""
    h, w = pre.gray.shape[:2]
    step = w / (len(COIN_TYPES) + 1)
    px_per_mm = step * 0.8 / max(t.diameter_mm for t in COIN_TYPES)
    return [
        Coin(coin_id=i, center_xy=(step * (i + 1), h / 2), radius_px=t.diameter_mm * px_per_mm / 2)
        for i, t in enumerate(COIN_TYPES)
    ]


__all__ = [
    "detect_coins",
    "detect_coin_at",
    "mock_detect_coins",
    "detect_coins_hough",
    "detect_coins_kmeans",
    "detect_coins_no_watershed",
]
