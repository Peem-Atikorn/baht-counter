"""ส่วนที่ 1: ปรับปรุงภาพและตรวจคุณภาพภาพ

    preprocess(image) -> PreprocessResult       # ย่อภาพ + ภาพเทาที่ปรับแล้ว + ตรวจคุณภาพ
    preprocess(image, enhance="he", white_balance=True)   # ตัวเลือกสำหรับการทดลอง (data/preprocess_experiment.py)
    image_quality(gray) -> ImageQuality         # ค่าที่ใช้ตัดสินคุณภาพ (ใช้ปรับเกณฑ์ด้วยชุด tune)
    mock_preprocess(image) -> PreprocessResult

เกณฑ์ทุกตัวเป็นค่าเริ่มต้นจากภาพสังเคราะห์ ต้องปรับด้วยภาพจริงในชุด tune
"""

from dataclasses import dataclass

import cv2
import numpy as np

from schemas import PreprocessResult

TARGET_LONG_SIDE = 1600

# ภาพเล็กเกินไป: ด้านสั้นต่ำกว่านี้ เหรียญ 25 สตางค์ในภาพ 3–30 เหรียญจะเหลือไม่กี่สิบพิกเซล
MIN_SHORT_SIDE = 480

# มืดเกินไป: แม้ส่วนที่สว่างที่สุดของภาพ (เปอร์เซ็นไทล์ 99) ยังมืด
# ไม่ใช้ค่าเฉลี่ย เพราะภาพเหรียญบนผ้าสีเข้มมีค่าเฉลี่ยต่ำแต่เหรียญยังสว่างชัด
DARK_P99_MAX = 80

# สว่างเกินไป: พิกเซลที่ขาวจนอิ่มตัว (>= 250) มีมากกว่าสัดส่วนนี้ของภาพ
CLIPPED_LEVEL = 250
CLIPPED_FRACTION_MAX = 0.6

# ไม่มีรายละเอียด: ขอบที่ชัดที่สุดของภาพยังอ่อนมาก (ภาพพื้นเรียบ ไม่มีเหรียญ หรือเลนส์ถูกบัง)
FLAT_EDGE_MAX = 15

# เบลอ: วัดความแปรปรวนของอนุพันธ์อันดับสอง (แบบ Laplacian) เฉพาะบริเวณขอบ (EDGE_PERCENTILE ขึ้นไป)
# - วัดทั้งภาพไม่ได้ เพราะพื้นหลังเรียบกินพื้นที่ส่วนใหญ่ ทำให้ภาพคมก็ได้ค่าต่ำ
# - แยกแนวนอน (d²/dx²) กับแนวตั้ง (d²/dy²) แล้วใช้ค่าที่ต่ำกว่า เพราะมือสั่นทำให้เบลอทางเดียว
#   Laplacian รวมสองแนวจะยังสูงจากขอบอีกแนวที่คมอยู่ (เหรียญกลมจึงมีขอบครบทุกทิศเมื่อภาพคม)
# ภาพสังเคราะห์ (ภาพ 1600 px): คม ≥ 2700, Gaussian σ=1 ≈ 370, σ=2 ≈ 50–160, มือสั่น 12 px ≈ 20–40
EDGE_PERCENTILE = 98
SHARPNESS_MIN = 100

CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)
MEDIAN_KSIZE = 5

# วิธีเพิ่มความต่างของภาพเทาก่อน median filter: none = ไม่ปรับ, he = Histogram Equalization ทั้งภาพ, clahe = ปรับทีละบริเวณ
ENHANCE_METHODS = ("none", "he", "clahe")

MSG_TOO_SMALL = "ภาพเล็กเกินไป กรุณาใช้ภาพที่ด้านสั้นอย่างน้อย {n} พิกเซล หรือถ่ายใหม่ด้วยความละเอียดเต็มของกล้อง"
MSG_TOO_DARK = "ภาพมืดเกินไป กรุณาเปิดไฟหรือถ่ายในที่สว่างขึ้น"
MSG_TOO_BRIGHT = "ภาพสว่างเกินไป กรุณาหลบแสงจ้าหรือปิดแฟลช"
MSG_FLAT = "ไม่พบรายละเอียดในภาพ กรุณาถ่ายให้เห็นเหรียญชัดเจนบนพื้นสีเรียบ"
MSG_BLURRY = "ภาพเบลอ กรุณาถือกล้องให้นิ่งและแตะหน้าจอให้โฟกัสที่เหรียญก่อนถ่าย"


@dataclass
class ImageQuality:
    short_side: int
    brightness_p99: float      # ความสว่างของส่วนที่สว่างที่สุด (0–255)
    clipped_fraction: float    # สัดส่วนพิกเซลที่ขาวจนอิ่มตัว
    edge_strength: float       # ความแรงขอบที่เปอร์เซ็นไทล์ EDGE_PERCENTILE
    sharpness: float           # min(var d²/dx², var d²/dy²) บริเวณขอบ


def image_quality(gray: np.ndarray) -> ImageQuality:
    """วัดค่าที่ใช้ตัดสินคุณภาพจากภาพเทาหลังย่อ (ก่อน CLAHE เพื่อให้เห็นแสงจริงของภาพ)"""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    edge_strength = float(np.percentile(magnitude, EDGE_PERCENTILE))
    edges = magnitude >= edge_strength
    dxx = cv2.Sobel(gray, cv2.CV_32F, 2, 0, ksize=3)
    dyy = cv2.Sobel(gray, cv2.CV_32F, 0, 2, ksize=3)
    sharpness = float(min(dxx[edges].var(), dyy[edges].var())) if edges.any() else 0.0
    return ImageQuality(
        short_side=min(gray.shape[:2]),
        brightness_p99=float(np.percentile(gray, 99)),
        clipped_fraction=float(np.mean(gray >= CLIPPED_LEVEL)),
        edge_strength=edge_strength,
        sharpness=sharpness,
    )


def quality_problem(q: ImageQuality) -> str | None:
    """เหตุผลภาษาไทยที่ภาพใช้ไม่ได้ หรือ None ถ้าใช้ได้ (ตรวจตามลำดับ ปัญหาที่แก้ง่ายที่สุดก่อน)"""
    if q.short_side < MIN_SHORT_SIDE:
        return MSG_TOO_SMALL.format(n=MIN_SHORT_SIDE)
    if q.brightness_p99 < DARK_P99_MAX:
        return MSG_TOO_DARK
    if q.clipped_fraction > CLIPPED_FRACTION_MAX:
        return MSG_TOO_BRIGHT
    if q.edge_strength < FLAT_EDGE_MAX:
        return MSG_FLAT
    if q.sharpness < SHARPNESS_MIN:
        return MSG_BLURRY
    return None


def _resize(image: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    factor = min(1.0, TARGET_LONG_SIDE / max(h, w))
    if factor < 1:
        image = cv2.resize(image, (round(w * factor), round(h * factor)), interpolation=cv2.INTER_AREA)
    return image, factor


def gray_world(image: np.ndarray) -> np.ndarray:
    """White balance แบบ gray world: ปรับแต่ละช่องสีให้ค่าเฉลี่ยเท่ากัน (สมมติว่าทั้งภาพโดยเฉลี่ยเป็นสีเทา)

    ข้อจำกัด: พื้นหลังที่มีสีเด่น (โต๊ะไม้, ผ้าสี) ดึงค่าเฉลี่ยเพี้ยน จึงต้องทดลองก่อนว่าช่วยจัดกลุ่มสีจริงไหม
    """
    means = image.reshape(-1, 3).mean(axis=0)
    gains = means.mean() / np.maximum(means, 1e-6)
    return np.clip(image.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def preprocess(image: np.ndarray, enhance: str = "clahe", white_balance: bool = False) -> PreprocessResult:
    """รับภาพ BGR ที่หมุนตาม EXIF แล้ว (app ทำตอนอ่านไฟล์)

    - `image`: ภาพสีหลังย่อ **ไม่ปรับสี** เพราะส่วนที่ 3 วัดสี HSV จากภาพนี้ (ยกเว้น white_balance=True)
    - `gray`: ภาพเทาหลัง CLAHE (เพิ่มความต่างระหว่างเหรียญกับพื้น) และ median filter (ลดจุดรบกวนและลายพื้นโต๊ะ)
    - ภาพที่ใช้ไม่ได้ได้ `status="failed"` พร้อม `reason` ภาษาไทย แต่ยังคืนภาพไว้ให้หน้า "เกี่ยวกับ" แสดงได้
    - `enhance` / `white_balance` ใช้เปรียบเทียบในการทดลอง ค่าเริ่มต้นคือวิธีที่ระบบใช้จริง
    """
    if enhance not in ENHANCE_METHODS:
        raise ValueError(f"enhance ต้องเป็นหนึ่งใน {ENHANCE_METHODS}: {enhance}")
    h, w = image.shape[:2]
    resized, factor = _resize(image)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    # ตรวจคุณภาพจากภาพก่อนปรับสีและความต่าง เพื่อให้เห็นแสงจริงของภาพ
    problem = quality_problem(image_quality(gray))

    debug_images = {"gray": gray}
    if white_balance:
        resized = gray_world(resized)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        debug_images["white_balanced"] = resized

    if enhance == "clahe":
        contrast = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID).apply(gray)
        debug_images["clahe"] = contrast
    elif enhance == "he":
        contrast = cv2.equalizeHist(gray)
        debug_images["he"] = contrast
    else:
        contrast = gray
    enhanced = cv2.medianBlur(contrast, MEDIAN_KSIZE)
    debug_images["enhanced"] = enhanced

    return PreprocessResult(
        image=resized,
        gray=enhanced,
        resize_factor=factor,
        original_size=(w, h),
        status="failed" if problem else "ok",
        reason=problem,
        debug_images=debug_images,
    )


def mock_preprocess(image: np.ndarray) -> PreprocessResult:
    """ย่อให้ด้านยาว TARGET_LONG_SIDE และแปลงเป็นภาพเทา ไม่ตรวจคุณภาพ"""
    h, w = image.shape[:2]
    resized, factor = _resize(image)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    return PreprocessResult(
        image=resized,
        gray=gray,
        resize_factor=factor,
        original_size=(w, h),
        status="ok",
        debug_images={"gray": gray},
    )
