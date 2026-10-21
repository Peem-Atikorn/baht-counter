"""Schema สำหรับ endpoint แก้ผล/ประวัติ/สถิติ — เพิ่มอย่างเดียว ไม่แก้ของเดิม
เปลี่ยน SCHEMA_VERSION เป็น 0.2.0 แล้ว (ดู models.py) ตามกติกาข้อ 3.3/AGENTS.md
"""

from pydantic import BaseModel

from .models import CoinCode, Status


class CoinUpdate(BaseModel):
    coin_type: CoinCode  # ชนิดที่ผู้ใช้เลือก — ใช้เป็น anchor คำนวณสเกลใหม่ทั้งภาพด้วย


class CoinCreate(BaseModel):
    xy: tuple[float, float]  # พิกัดที่ผู้ใช้กดบนภาพต้นฉบับ (ก่อนย่อ)


class HistoryItem(BaseModel):
    analysis_id: str
    created_at: str  # ISO 8601 (UTC)
    status: Status
    total_baht: float | None
    coin_count: int


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int


class StatsResponse(BaseModel):
    analyses_count: int
    avg_timings_sec: dict[str, float]  # ค่าเฉลี่ยเวลาแต่ละขั้น (preprocess/detection/classification)
    total_edits: int  # จำนวนครั้งที่ผู้ใช้แก้ผลทั้งหมด (PUT/POST/DELETE coins) ของทุกภาพ
    edits_per_analysis_avg: float


class HealthResponse(BaseModel):
    status: str
