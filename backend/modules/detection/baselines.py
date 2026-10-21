"""อัลกอริทึม Baseline สำหรับใช้เปรียบเทียบในรายงาน (Hough, K-Means, Non-watershed)"""

from __future__ import annotations

import cv2
import numpy as np

from modules.detection.fit import extract_coins_from_markers
from modules.detection.segment import clean_morphology, segment_coins_otsu
from schemas import Coin, PreprocessResult


def detect_coins_hough(
    pre: PreprocessResult,
    dp: float = 1.2,
    min_dist_ratio: float = 0.04,
    param1: float = 50,
    param2: float = 30,
    min_radius_ratio: float = 0.015,
    max_radius_ratio: float = 0.25,
) -> list[Coin]:
    """วิธีเปรียบเทียบ: Hough Circle Transform จาก OpenCV

    ค้นหาวงกลมโดยตรงจาก Grayscale Image เหมาะสำหรับใช้เป็นวิธีพื้นฐานเปรียบเทียบในรายงาน
    """
    gray = pre.gray
    h, w = gray.shape[:2]
    dim_min = min(h, w)

    min_dist = max(10, int(dim_min * min_dist_ratio))
    min_r = max(5, int(dim_min * min_radius_ratio))
    max_r = max(min_r + 10, int(dim_min * max_radius_ratio))

    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=dp,
        minDist=min_dist,
        param1=param1,
        param2=param2,
        minRadius=min_r,
        maxRadius=max_r,
    )

    coins: list[Coin] = []
    if circles is not None:
        circles_arr = np.round(circles[0, :]).astype(int)
        for i, (cx, cy, r) in enumerate(circles_arr):
            coins.append(
                Coin(
                    coin_id=i,
                    center_xy=(float(cx), float(cy)),
                    radius_px=float(r),
                    ellipse=None,
                    source="estimated",
                    status="ok",
                )
            )

    coins.sort(key=lambda c: c.center_xy[0])
    for idx, c in enumerate(coins):
        coins[idx] = c.model_copy(update={"coin_id": idx})

    return coins


def detect_coins_kmeans(
    pre: PreprocessResult,
    k: int = 3,
    min_area_px: float = 100.0,
) -> list[Coin]:
    """วิธีเปรียบเทียบ: K-Means Clustering บนภาพสี BGR สำหรับแยกเหรียญออกจากพื้นหลัง"""
    image = pre.image
    pixels = image.reshape((-1, 3)).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)

    # แปลงผลกลับเป็นภาพขนาดเดิม
    h, w = image.shape[:2]
    label_img = labels.reshape((h, w))

    # หาว่า cluster ใดคือพื้นหลังโดยดูจากพิกเซลขอบภาพ
    border_labels = np.concatenate([
        label_img[0, :], label_img[-1, :], label_img[:, 0], label_img[:, -1]
    ])
    bg_cluster = int(np.bincount(border_labels).argmax())

    # Foreground คือทุก cluster ที่ไม่ใช่พื้นหลัง
    fg_mask = (label_img != bg_cluster).astype(np.uint8) * 255
    cleaned_mask = clean_morphology(fg_mask)

    # กำหนดหมายเลข Connected Components
    num_labels, comp_markers = cv2.connectedComponents(cleaned_mask)
    # เลื่อนหมายเลข label เพื่อให้สอดคล้องกับ marker convention: background = 1, coins >= 2
    comp_markers = comp_markers + 1

    return extract_coins_from_markers(comp_markers, clean_mask=cleaned_mask, min_area_px=min_area_px)


def detect_coins_no_watershed(
    pre: PreprocessResult,
    min_area_px: float = 100.0,
) -> list[Coin]:
    """วิธีเปรียบเทียบ: Thresholding + Morphology โดยไม่ใช้ Watershed (สำหรับวัดผลเหรียญชิดกัน)"""
    mask = segment_coins_otsu(pre.gray)
    clean_mask = clean_morphology(mask)

    num_labels, comp_markers = cv2.connectedComponents(clean_mask)
    comp_markers = comp_markers + 1

    return extract_coins_from_markers(comp_markers, clean_mask=clean_mask, min_area_px=min_area_px)
