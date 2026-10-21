"""ส่วนที่ 1: ปรับปรุงภาพและตรวจคุณภาพภาพ"""

import cv2
import numpy as np

from schemas import PreprocessResult

TARGET_LONG_SIDE = 1600


def preprocess(image: np.ndarray) -> PreprocessResult:
    """รับภาพ BGR ที่หมุนตาม EXIF แล้ว (app ทำตอนอ่านไฟล์)

    TODO(ส่วนที่ 1, สัปดาห์ 2): CLAHE, median filter, ตรวจเบลอ (Laplacian variance),
    มืด/สว่างเกิน, ภาพเล็กเกินไป พร้อม reason ภาษาไทย
    """
    raise NotImplementedError("preprocess ยังไม่เสร็จ ใช้ mock_preprocess ไปก่อน")


def mock_preprocess(image: np.ndarray) -> PreprocessResult:
    """ย่อให้ด้านยาว TARGET_LONG_SIDE และแปลงเป็นภาพเทา ไม่ตรวจคุณภาพ"""
    h, w = image.shape[:2]
    factor = min(1.0, TARGET_LONG_SIDE / max(h, w))
    resized = cv2.resize(image, (round(w * factor), round(h * factor)), interpolation=cv2.INTER_AREA) if factor < 1 else image
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    return PreprocessResult(
        image=resized,
        gray=gray,
        resize_factor=factor,
        original_size=(w, h),
        status="ok",
        debug_images={"gray": gray},
    )
