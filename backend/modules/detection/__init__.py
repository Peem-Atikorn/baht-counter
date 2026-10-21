"""ส่วนที่ 2: หาตำแหน่งเหรียญ (Coin Detection)

ไปป์ไลน์หลัก:
PreprocessResult -> Multi-cue Segmentation -> Morphology -> Distance Transform -> Component-Guided Watershed -> Fit Ellipse -> list[Coin]
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
from modules.detection.segment import clean_morphology, segment_coins
from modules.detection.watershed import apply_watershed
from schemas import COIN_TYPES, Coin, PreprocessResult


def detect_coins(pre: PreprocessResult) -> list[Coin]:
    """ค้นหาเหรียญทั้งหมดในภาพ คืน list[Coin] ที่มี center_xy, radius_px, ellipse

    ใช้เทคนิค:
    1. Multi-cue Segmentation: ผสาน Grayscale Otsu (ชดเชยแสงไม่สม่ำเสมอ/เงา) และ Color Difference
    2. Morphological Closing (เติมรูในเหรียญและแสงสะท้อน) + Opening (ตัด noise)
    3. Distance Transform + Local Maxima Peak Finding เพื่อสร้าง Seeds
    4. Component-Guided Watershed Segmentation ตัดแบ่งเหรียญที่วางสัมผัส/ชิดกัน
    5. Fit Ellipse ต่อเหรียญ โดยใช้แกนยาว (Major Axis) รองรับภาพถ่ายมุมเอียง
    6. กรองขนาดผิดปกติเมื่อเทียบกับเหรียญอื่นในภาพ
    7. บันทึกภาพกลางทางลง pre.debug_images สำหรับหน้า 'เกี่ยวกับ'
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
    - ค้นหาเฉพาะในบริเวณ ROI รอบจุดที่กด (เร็ว < 10ms และไม่เขียนทับ pre.debug_images)
    - ปรับขนาด ROI ตามสัดส่วนของภาพ
    - กรองไม่รับ Contour ที่แตะขอบเขต ROI และกรองความกลม เพื่อป้องกันเหรียญปลอมจาก noise/ลายไม้
    """
    x, y = xy
    h, w = pre.gray.shape[:2]

    # ตรวจสอบว่าพิกัดอยู่ในขอบเขตภาพหรือไม่
    if not (0 <= x < w and 0 <= y < h):
        return None

    # ปรับขนาด ROI ตามสัดส่วนของขนาดภาพ (รองรับเหรียญขนาดใหญ่ r=230px+)
    roi_radius = max(90, min(320, int(min(h, w) * 0.28)))
    x1, y1 = max(0, int(x - roi_radius)), max(0, int(y - roi_radius))
    x2, y2 = min(w, int(x + roi_radius)), min(h, int(y + roi_radius))
    if x2 - x1 < 30 or y2 - y1 < 30:
        return None

    roi_gray = pre.gray[y1:y2, x1:x2]
    roi_bgr = pre.image[y1:y2, x1:x2] if len(pre.image.shape) == 3 else cv2.cvtColor(roi_gray, cv2.COLOR_GRAY2BGR)
    roi_h, roi_w = roi_gray.shape[:2]
    local_click = (x - x1, y - y1)

    # ตรวจสอบว่าบริเวณนี้มีรายละเอียด/ความแตกต่างของแสงเพียงพอหรือไม่
    if float(np.std(roi_gray)) < 6.0:
        return None

    # ตัดแยกเหรียญใน ROI
    roi_mask = segment_coins(roi_bgr, roi_gray)
    clean_roi_mask = clean_morphology(roi_mask)

    contours, _ = cv2.findContours(clean_roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_coin: Coin | None = None
    min_dist_to_center = float("inf")

    for cnt in contours:
        # 1. ไม่รับ Contour ที่แตะขอบ ROI (เพื่อตัด noise หรือพื้นหลังที่ถูกแบ่งครึ่ง)
        pts = cnt.reshape(-1, 2)
        if (
            np.any(pts[:, 0] <= 1)
            or np.any(pts[:, 0] >= roi_w - 2)
            or np.any(pts[:, 1] <= 1)
            or np.any(pts[:, 1] >= roi_h - 2)
        ):
            continue

        # 2. กรองขนาดพื้นที่
        area = float(cv2.contourArea(cnt))
        if area < 120.0 or area > np.pi * (roi_radius * 0.98) ** 2:
            continue

        # 3. กรองความกลม (Circularity >= 0.60)
        perimeter = float(cv2.arcLength(cnt, True))
        if perimeter <= 0:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < 0.60:
            continue

        # 4. จุดที่คลิกต้องอยู่ภายในหรือใกล้กับขอบเขตเหรียญ
        dist_to_contour = cv2.pointPolygonTest(cnt, local_click, True)
        if dist_to_contour < -10.0:
            continue

        # 5. Fit Ellipse / Circle
        if len(cnt) >= 5:
            try:
                (lcx, lcy), (d1, d2), angle = cv2.fitEllipse(cnt)
                major = float(max(d1, d2))
                minor = float(min(d1, d2))
                if major <= 0 or (minor / major) < 0.50:
                    continue
                r = major / 2.0
                ellipse = (major, minor, float(angle))
            except cv2.error:
                (lcx, lcy), r = cv2.minEnclosingCircle(cnt)
                ellipse = None
        else:
            (lcx, lcy), r = cv2.minEnclosingCircle(cnt)
            ellipse = None

        if r > roi_radius * 0.98:
            continue

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

    # ถ้ายังไม่เจอ ลองตรวจหาด้วย Hough Circles ภายใน ROI
    blurred = cv2.GaussianBlur(roi_gray, (7, 7), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=20,
        param1=50,
        param2=25,
        minRadius=15,
        maxRadius=int(roi_radius * 0.90),
    )
    if circles is not None:
        for cx_l, cy_l, r_l in circles[0]:
            # ไม่รับวงกลมที่แตะขอบ ROI
            if (
                cx_l - r_l <= 1
                or cx_l + r_l >= roi_w - 2
                or cy_l - r_l <= 1
                or cy_l + r_l >= roi_h - 2
            ):
                continue

            if np.hypot(cx_l - local_click[0], cy_l - local_click[1]) <= r_l * 1.1:
                gcx, gcy = cx_l + x1, cy_l + y1
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
