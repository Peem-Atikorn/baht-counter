"""Schema กลาง (หัวข้อ 3.3) — แก้ไฟล์นี้ต้องเปิด PR ที่ทุกคนเห็น และเพิ่ม SCHEMA_VERSION"""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pydantic import BaseModel

SCHEMA_VERSION = "0.2.1"

Status = Literal["ok", "needs_confirmation", "failed"]
ColorGroup = Literal["copper", "silver", "gold", "bimetal", "unknown"]
CoinCode = Literal["THB_0_25", "THB_0_50", "THB_1", "THB_2", "THB_5", "THB_10", "unknown"]
CoinSource = Literal["estimated", "user_edited", "user_added"]


class Coin(BaseModel):
    coin_id: int
    # ในโมดูลเป็นพิกัดของภาพหลัง preprocess; pipeline แปลงกลับเป็นพิกัดภาพต้นฉบับ (หลังหมุนตาม EXIF) ก่อนส่ง frontend
    center_xy: tuple[float, float]
    radius_px: float
    ellipse: tuple[float, float, float] | None = None  # แกนยาว, แกนสั้น (px), มุม (องศา)
    color_group: ColorGroup = "unknown"
    coin_type: CoinCode | None = None
    value_baht: float | None = None
    confidence: float | None = None
    source: CoinSource = "estimated"
    status: Status = "ok"
    reason: str | None = None


class CountResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    image_size: tuple[int, int]  # (width, height)
    coins: list[Coin]
    total_baht: float | None
    scale_mm_per_px: float | None
    scale_source: Literal["inferred", "user_anchor"] | None
    status: Status
    reason: str | None
    debug_images: dict[str, str] = {}  # ชื่อภาพกลางทาง -> URL สำหรับหน้า "เกี่ยวกับ"


class CoinTypeInfo(BaseModel):
    code: CoinCode
    name_th: str
    value_baht: float
    diameter_mm: float
    color_group: ColorGroup
    display_color: str


class AnalysisResponse(BaseModel):
    analysis_id: str
    result: CountResult


@dataclass
class PreprocessResult:
    """ผลของส่วนที่ 1 — ใช้ภายใน backend เท่านั้น (มีภาพ numpy จึงไม่ใช่ Pydantic)"""

    image: np.ndarray  # BGR หลังย่อ
    gray: np.ndarray  # ภาพเทาหลังปรับปรุง
    resize_factor: float  # ขนาดที่ย่อ / ขนาดต้นฉบับ; หารพิกัดด้วยค่านี้เพื่อกลับไปเป็นพิกัดต้นฉบับ
    original_size: tuple[int, int]  # (width, height)
    status: Status
    reason: str | None = None
    debug_images: dict[str, np.ndarray] = field(default_factory=dict)
