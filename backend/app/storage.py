"""เก็บไฟล์ภาพของแต่ละผลการนับไว้ใต้ BAHT_DATA_DIR (ค่าเริ่มต้น storage/) ไม่หายเมื่อรีสตาร์ท
ชื่อไฟล์ (ไม่ใช่ path เต็ม) ถูกเก็บเป็น URL ใน debug_images ของ CountResult (ดู db.py)
"""

import os
from pathlib import Path


def data_dir() -> Path:
    """อ่าน BAHT_DATA_DIR ทุกครั้งที่เรียก (ไม่แคช) เพื่อให้เทสต์สลับโฟลเดอร์ชั่วคราวได้"""
    d = Path(os.getenv("BAHT_DATA_DIR", "storage"))
    (d / "images").mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "baht.db"


def _analysis_dir(analysis_id: str) -> Path:
    d = data_dir() / "images" / analysis_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_image(analysis_id: str, filename: str, data: bytes) -> None:
    (_analysis_dir(analysis_id) / filename).write_bytes(data)


def load_image(analysis_id: str, filename: str) -> bytes | None:
    path = _analysis_dir(analysis_id) / filename
    if not path.is_file():
        return None
    return path.read_bytes()
