"""การวิเคราะห์ Contour, การ Fit วงรี/วงกลม และการกรองวัตถุที่ไม่ใช่เหรียญ"""

from __future__ import annotations

import cv2
import numpy as np

from schemas import Coin


def filter_size_relative_to_coins(coins: list[Coin]) -> list[Coin]:
    """กรองเหรียญที่มีขนาดผิดปกติเมื่อเทียบกับเหรียญอื่นในภาพเดียวกัน

    ตามขนาดจริงของเหรียญไทย:
    - เหรียญเล็กสุด: 25 สตางค์ (16 มม.)
    - เหรียญใหญ่สุด: 10 บาท (26 มม.)
    อัตราส่วนขนาดใหญ่สุด/เล็กสุดบนระนาบเดียวกันคือ 26 / 16 = 1.625
    เมื่อคิดมุมกล้องเอียง 30 องศา อัตราส่วนไม่ควรเกิน ~2.2 เท่าของมัธยฐาน
    หากมีเหรียญตั้งแต่ 3 เหรียญขึ้นไป วัตถุที่รัศมีหลุดช่วง (0.45 * median ถึง 2.2 * median) จะถูกกรองออก
    """
    if len(coins) < 3:
        return coins

    radii = [c.radius_px for c in coins]
    median_r = float(np.median(radii))
    if median_r <= 0:
        return coins

    min_valid_r = 0.45 * median_r
    max_valid_r = 2.20 * median_r

    filtered = [c for c in coins if min_valid_r <= c.radius_px <= max_valid_r]
    for idx, c in enumerate(filtered):
        filtered[idx] = c.model_copy(update={"coin_id": idx})
    return filtered


def extract_coins_from_markers(
    markers: np.ndarray,
    clean_mask: np.ndarray | None = None,
    min_area_px: float = 250.0,
    min_circularity: float = 0.65,
    min_aspect_ratio: float = 0.50,
    filter_relative_size: bool = True,
) -> list[Coin]:
    """สกัดรายการเหรียญจากผลลัพธ์ของ Watershed markers (หรือ Connected Components)

    แต่ละ Region ที่มี Label >= 2 จะถูกนำมาวิเคราะห์รูปทรง:
    - หา Contour ภายนอก
    - ตรวจสอบพื้นที่ (Area) และความกลม (Circularity: 4 * pi * Area / Perimeter^2)
    - Fit Ellipse: ใช้แกนยาว (Major Axis) เป็นเส้นผ่านศูนย์กลาง เพื่อชดเชยมุมกล้องเอียง
    - กรองขนาดเปรียบเทียบกับเหรียญอื่นในภาพ (สามารถปิดได้เมื่อใช้กับอัลกอริทึม Baseline)
    """
    coins: list[Coin] = []
    h, w = markers.shape[:2]
    max_area_px = 0.6 * (h * w)

    unique_labels = np.unique(markers)
    # ตัด label 1 (พื้นหลัง) และ -1 (เส้นแบ่งขอบเขต)
    coin_labels = [lbl for lbl in unique_labels if lbl >= 2]
    reclaim_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    for lbl in coin_labels:
        region_mask = (markers == lbl).astype(np.uint8) * 255
        # คืนพิกัดขอบเขต (-1) ที่ watershed ตัดออก กลับคืนมาโดยอิงจาก clean_mask เดิม
        if clean_mask is not None:
            region_mask = cv2.dilate(region_mask, reclaim_kernel) & clean_mask

        contours, _ = cv2.findContours(region_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        cnt = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(cnt))

        # 1. กรองขนาดพื้นที่
        if area < min_area_px or area > max_area_px:
            continue

        perimeter = float(cv2.arcLength(cnt, True))
        if perimeter <= 0:
            continue

        # 2. กรองความกลม (Circularity)
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < min_circularity:
            continue

        # 3. Fit วงรี / ประมาณวงกลม
        if len(cnt) >= 5:
            try:
                (cx, cy), (axis1, axis2), angle = cv2.fitEllipse(cnt)
                major_axis = float(max(axis1, axis2))
                minor_axis = float(min(axis1, axis2))

                # กรองอัตราส่วนแกนสั้น/แกนยาว (ไม่แบนเกินไป)
                aspect_ratio = minor_axis / major_axis if major_axis > 0 else 0.0
                if major_axis > 0 and aspect_ratio < min_aspect_ratio:
                    continue

                # ประมาณรัศมี:
                # - ภาพมุมตรงหรือเอียงเล็กน้อย (aspect >= 0.88): ใช้ค่าเฉลี่ยกึ่งแกน (major + minor) / 4.0
                #   เพื่อลดผลกระทบจาก noise ขอบหยักและเงา ทำให้ความคลาดเคลื่อนของรัศมีลดลงอย่างมีนัยสำคัญ
                # - ภาพมุมเอียงชัดเจน (aspect < 0.88): ใช้แกนยาว major / 2.0 ซึ่งเป็นมิติที่ไม่ถูกบีบอัดตามมุมมองกล้อง
                if aspect_ratio >= 0.88:
                    radius_px = (major_axis + minor_axis) / 4.0
                else:
                    radius_px = major_axis / 2.0

                ellipse_tuple: tuple[float, float, float] | None = (major_axis, minor_axis, float(angle))
                center_xy = (float(cx), float(cy))
            except cv2.error:
                (cx, cy), r = cv2.minEnclosingCircle(cnt)
                radius_px = float(r)
                ellipse_tuple = None
                center_xy = (float(cx), float(cy))
        else:
            (cx, cy), r = cv2.minEnclosingCircle(cnt)
            radius_px = float(r)
            ellipse_tuple = None
            center_xy = (float(cx), float(cy))

        if radius_px <= 0:
            continue

        coins.append(
            Coin(
                coin_id=0,
                center_xy=center_xy,
                radius_px=radius_px,
                ellipse=ellipse_tuple,
                source="estimated",
                status="ok",
            )
        )

    # กรองขนาดเมื่อเทียบกับเหรียญอื่นในภาพ (ถ้าเปิดใช้งาน)
    if filter_relative_size:
        coins = filter_size_relative_to_coins(coins)

    # จัดเรียงเหรียญจากซ้ายไปขวา (ตามแกน X) เพื่อความสม่ำเสมอ และกำหนด coin_id
    coins.sort(key=lambda c: (c.center_xy[0]))
    for idx, c in enumerate(coins):
        coins[idx] = c.model_copy(update={"coin_id": idx})

    return coins
