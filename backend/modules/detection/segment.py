"""การแยกเหรียญออกจากพื้นหลัง (Segmentation) และการปรับแต่งสัณฐานวิทยา (Morphology)"""

from __future__ import annotations

import cv2
import numpy as np


def estimate_background_color(image: np.ndarray, border_width: int = 8) -> np.ndarray:
    """ประเมินสีพื้นหลัง (BGR) จากพิกเซลขอบภาพทั้ง 4 ด้าน"""
    h, w = image.shape[:2]
    bw = max(1, min(border_width, h // 10, w // 10))
    border_pixels = np.vstack([
        image[:bw, :].reshape(-1, 3),
        image[-bw:, :].reshape(-1, 3),
        image[:, :bw].reshape(-1, 3),
        image[:, -bw:].reshape(-1, 3),
    ])
    return np.median(border_pixels, axis=0)


def fill_internal_holes(mask: np.ndarray) -> np.ndarray:
    """เติมรูภายในวัตถุ (เช่น แสงสะท้อนสีขาว รูในเหรียญ หรือลวดลาย) ให้เป็นแผ่นตัน"""
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    filled = mask.copy()
    if hierarchy is not None:
        for i, h in enumerate(hierarchy[0]):
            if h[3] != -1:
                cv2.drawContours(filled, contours, i, 255, -1)
    return filled


def flatten_illumination(gray: np.ndarray, sigma: float = 50.0) -> np.ndarray:
    """ชดเชยแสงไม่สม่ำเสมอ/ขอบมืด/เงา (Illumination Gradient)

    ประมาณความสว่างพื้นหลังด้วย Large Gaussian Filter แล้วลบออก ปรับระดับค่าให้อยู่ที่ 128
    """
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)
    diff = gray.astype(np.float32) - bg.astype(np.float32) + 128.0
    return np.clip(diff, 0, 255).astype(np.uint8)


def segment_coins_otsu(gray: np.ndarray, blur_ksize: int = 5) -> np.ndarray:
    """แยกเหรียญด้วย Otsu Thresholding บนภาพ Grayscale พร้อมปรับตามสีพื้นหลังอัตโนมัติ"""
    if blur_ksize > 1:
        blurred = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    else:
        blurred = gray

    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # ตรวจสอบขอบภาพ หากขอบภาพเป็นสีขาว (พื้นหลังสว่าง) ให้ invert
    h, w = thresh.shape[:2]
    bw = max(1, min(10, h // 20, w // 20))
    border_pixels = np.concatenate([
        thresh[:bw, :].flatten(),
        thresh[-bw:, :].flatten(),
        thresh[:, :bw].flatten(),
        thresh[:, -bw:].flatten(),
    ])
    if np.mean(border_pixels) > 127:
        thresh = cv2.bitwise_not(thresh)

    return thresh


def segment_coins(
    image: np.ndarray,
    gray: np.ndarray,
    blur_ksize: int = 5,
) -> np.ndarray:
    """แยกเหรียญโดยผสานข้อมูลทั้ง Grayscale Contrast และ Color Difference กับสีพื้นหลัง

    - หากพื้นหลังมีแสงไม่สม่ำเสมอ (ไล่ระดับแสง/เงา) จะทำ Illumination Flattening ก่อน Threshold
    - คำนวณความต่างสีโดยใช้ np.clip ป้องกันค่าเกิน 255 ไม่ให้วนกลับ (Overflow)
    """
    h, w = gray.shape[:2]
    bw = max(1, min(10, h // 20, w // 20))
    border_gray = np.concatenate([
        gray[:bw, :].flatten(),
        gray[-bw:, :].flatten(),
        gray[:, :bw].flatten(),
        gray[:, -bw:].flatten(),
    ])

    # ตรวจสอบว่าพื้นหลังมีการไล่ระดับแสงมากหรือไม่ (เช่น แสงไม่สม่ำเสมอ เงา ขอบมืด)
    has_uneven_light = float(np.std(border_gray)) > 10.0
    if has_uneven_light:
        sigma = max(35.0, min(h, w) * 0.08)
        processed_gray = flatten_illumination(gray, sigma=sigma)
    else:
        processed_gray = gray

    # 1. Grayscale Otsu
    mask_gray = segment_coins_otsu(processed_gray, blur_ksize=blur_ksize)

    # 2. Color Difference กับสีพื้นหลัง (BGR Euclidean Distance)
    if len(image.shape) == 3 and image.shape[2] == 3:
        if has_uneven_light:
            sigma = max(35.0, min(h, w) * 0.08)
            bg_col = cv2.GaussianBlur(image, (0, 0), sigmaX=sigma, sigmaY=sigma)
            color_diff = np.clip(
                np.linalg.norm(image.astype(np.float32) - bg_col.astype(np.float32), axis=2),
                0,
                255,
            ).astype(np.uint8)
        else:
            border_bgr = np.vstack([
                image[:bw, :].reshape(-1, 3),
                image[-bw:, :].reshape(-1, 3),
                image[:, :bw].reshape(-1, 3),
                image[:, -bw:].reshape(-1, 3),
            ])
            bg_bgr = np.median(border_bgr, axis=0)
            color_diff = np.clip(
                np.linalg.norm(image.astype(np.float32) - bg_bgr.astype(np.float32), axis=2),
                0,
                255,
            ).astype(np.uint8)

        blurred_diff = cv2.GaussianBlur(color_diff, (blur_ksize, blur_ksize), 0)
        _, mask_color = cv2.threshold(blurred_diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # ตรวจสอบขอบของ mask_color
        border_pixels = np.concatenate([
            mask_color[:bw, :].flatten(),
            mask_color[-bw:, :].flatten(),
            mask_color[:, :bw].flatten(),
            mask_color[:, -bw:].flatten(),
        ])
        if np.mean(border_pixels) > 127:
            mask_color = cv2.bitwise_not(mask_color)

        combined = cv2.bitwise_or(mask_gray, mask_color)
    else:
        combined = mask_gray

    return combined


def clean_morphology(
    mask: np.ndarray,
    close_size: int = 9,
    open_size: int = 3,
) -> np.ndarray:
    """ปรับปรุงหน้ากาก binary ด้วย Closing (ปิดรูในเหรียญ) และ Opening (ตัดจุดรบกวนภายนอก)"""
    if close_size > 1:
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    mask = fill_internal_holes(mask)

    if open_size > 1:
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

    return mask
