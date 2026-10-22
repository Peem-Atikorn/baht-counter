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


def fill_internal_holes(mask: np.ndarray, max_hole_area: float | None = None) -> np.ndarray:
    """เติมรูภายในวัตถุ (เช่น แสงสะท้อนสีขาว รูในเหรียญ หรือลวดลาย) ให้เป็นแผ่นตัน

    หากระบุ max_hole_area จะเติมเฉพาะรูที่มีขนาดเล็กกว่าเกณฑ์ เพื่อป้องกันไม่ให้ช่องว่าง
    ระหว่างเหรียญหลายเหรียญหรือพื้นหลังลายผ้าถูกเชื่อมรวมกลายเป็นก้อนเดียวกัน
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    filled = mask.copy()
    if hierarchy is not None:
        for i, h in enumerate(hierarchy[0]):
            if h[3] != -1:
                if max_hole_area is None or cv2.contourArea(contours[i]) <= max_hole_area:
                    cv2.drawContours(filled, contours, i, 255, -1)
    return filled


def estimate_bg_illumination_gray(gray: np.ndarray, scale: float = 0.0625, ksize: int = 71) -> np.ndarray:
    """ประเมินพื้นหลังของภาพเทาด้วย Downsampled Median Filter

    หมายเหตุเรื่อง ksize: การย่อภาพ 16x (scale=0.0625) ทำให้ภาพขนาด 1200x1600 เหลือราว 75x100
    แต่ยังคง ksize=71 ไว้ เนื่องจากกลุ่มเหรียญที่วางติดกันหลายเหรียญ (Cluster) อาจมีความกว้างบนภาพย่อ
    ถึง 30-40 พิกเซล หากลด ksize ลงมาตามสัดส่วน (เช่น 35 หรือ 25) หน้าต่างมัธยฐานจะเล็กกว่ากลุ่มเหรียญ
    ทำให้ค่ามัธยฐานกลืนเนื้อเหรียญกลายเป็นพื้นหลังและสูญเสีย Recall อย่างมีนัยสำคัญ
    การคง ksize=71 จึงช่วยรักษาเหรียญในกลุ่มหนาแน่นได้ดีที่สุด ขณะที่ยังสามารถประมาณแนวโน้มแสงกว้างๆ
    (Global Illumination Trend / Vignette) ข้ามทั้งภาพได้
    """
    h, w = gray.shape[:2]
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    k = min(ksize, small.shape[0] - 1 if small.shape[0] % 2 == 1 else small.shape[0] - 2)
    k = max(15, k if k % 2 == 1 else k + 1)
    bg_small = cv2.medianBlur(small, k)
    return cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_CUBIC)


def estimate_bg_illumination_bgr(bgr: np.ndarray, scale: float = 0.0625, ksize: int = 71) -> np.ndarray:
    """ประเมินภาพพื้นหลังของภาพสี (BGR) ด้วย Downsampled Median Filter

    (ใช้หลักการเดียวกับ estimate_bg_illumination_gray โดยคง ksize=71 เพื่อป้องกันไม่ให้กลืนกลุ่มเหรียญหนาแน่น)
    """
    h, w = bgr.shape[:2]
    small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    k = min(ksize, small.shape[0] - 1 if small.shape[0] % 2 == 1 else small.shape[0] - 2)
    k = max(15, k if k % 2 == 1 else k + 1)
    bg_small = cv2.medianBlur(small, k)
    return cv2.resize(bg_small, (w, h), interpolation=cv2.INTER_CUBIC)


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

    - หากพื้นหลังมีแสงไม่สม่ำเสมอ (ไล่ระดับแสง/เงา/ขอบมืด) จะใช้ Downsampled Median Background Subtraction
      ซึ่งรองรับเหรียญทุกขนาด (เล็กสุด 16px ถึง ใหญ่สุด 260px) โดยไม่มีปัญหาเหรียญใหญ่ถูกตัดขอบ
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

    # ตรวจสอบว่าพื้นหลังมีการไล่ระดับแสงมากหรือไม่
    has_uneven_light = float(np.std(border_gray)) > 10.0
    if has_uneven_light:
        bg_gray = estimate_bg_illumination_gray(gray)
        processed_gray = np.clip(
            gray.astype(np.float32) - bg_gray.astype(np.float32) + 128.0, 0, 255
        ).astype(np.uint8)
    else:
        processed_gray = gray

    # 1. Grayscale Otsu
    mask_gray = segment_coins_otsu(processed_gray, blur_ksize=blur_ksize)

    # 2. Color Difference กับสีพื้นหลัง (BGR Euclidean Distance)
    if len(image.shape) == 3 and image.shape[2] == 3:
        if has_uneven_light:
            bg_col = estimate_bg_illumination_bgr(image)
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
    close_size: int = 7,
    open_size: int = 5,
) -> np.ndarray:
    """ปรับปรุงหน้ากาก binary ด้วย Closing (ปิดรูในเหรียญ) และ Opening (ตัดจุดรบกวนภายนอกและเส้นใยผ้า)"""
    h, w = mask.shape[:2]
    # รัศมี 0.22 * min(h, w) อ้างอิงจากขนาดเหรียญ 10 บาทที่มีขนาดใหญ่ที่สุด (25.6 มม.)
    # ตามโปรโตคอลการถ่ายภาพ (docs/photo-protocol.md) จะมีรัศมีไม่เกิน ~18-20% ของด้านสั้นของภาพ
    # การกำหนดรัศมีขอบเขตสูงสุดของรูภายในเหรียญเป็น 0.22 * min(h, w) (หรือพื้นที่ π * r^2)
    # จึงครอบคลุมพื้นที่เหรียญเดี่ยว 1 เหรียญได้อย่างปลอดภัย เพื่อปิดรูแสงสะท้อนหรือลวดลายในเหรียญ
    # โดยไม่เชื่อมต่อช่องว่างลายผ้าหรือพื้นหลังระหว่างเหรียญหลายวงเข้าด้วยกัน
    max_hole = np.pi * (min(h, w) * 0.22) ** 2

    if close_size > 1:
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)

    mask = fill_internal_holes(mask, max_hole_area=max_hole)

    if open_size > 1:
        kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_size, open_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)

    return mask
