"""เก็บผลการนับ (ไม่ใช่ตัวภาพ ดู storage.py) ใน SQLite ใต้ BAHT_DATA_DIR — ไม่หายเมื่อรีสตาร์ท

โมดูลประมวลผลภาพ (backend/modules/*) เป็นฟังก์ชันบริสุทธิ์ ไม่แตะฐานข้อมูลเอง (AGENTS.md)
ไฟล์นี้เป็นส่วนที่ 4 (backend/app/) จึงเป็นที่เดียวที่อ่าน/เขียนฐานข้อมูล
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from schemas import CountResult

from . import storage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    original_filename TEXT,
    original_ext TEXT NOT NULL,
    result_json TEXT NOT NULL,
    timings_json TEXT NOT NULL,
    edit_count INTEGER NOT NULL DEFAULT 0
)
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(storage.db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)  # IF NOT EXISTS — ทำให้ไม่ต้องสนลำดับการเรียก init_db()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect():
        pass  # แค่สร้างตารางถ้ายังไม่มี (ดู _connect)


def _row_to_record(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "original_filename": row["original_filename"],
        "original_ext": row["original_ext"],
        "result": CountResult.model_validate_json(row["result_json"]),
        "timings": json.loads(row["timings_json"]),
        "edit_count": row["edit_count"],
    }


def insert_analysis(
    analysis_id: str,
    result: CountResult,
    timings: dict[str, float],
    original_filename: str | None,
    original_ext: str,
) -> str:
    """คืนเวลาที่สร้าง (created_at, ISO 8601 UTC)"""
    created_at = datetime.now(UTC).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO analyses"
            " (id, created_at, original_filename, original_ext, result_json, timings_json, edit_count)"
            " VALUES (?, ?, ?, ?, ?, ?, 0)",
            (
                analysis_id,
                created_at,
                original_filename,
                original_ext,
                result.model_dump_json(),
                json.dumps(timings),
            ),
        )
    return created_at


def get_analysis(analysis_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    return _row_to_record(row) if row else None


def update_result(analysis_id: str, result: CountResult) -> None:
    """บันทึกผลที่แก้แล้ว และนับเป็น 1 ครั้งที่ผู้ใช้แก้ผล (ใช้ใน /api/stats)"""
    with _connect() as conn:
        conn.execute(
            "UPDATE analyses SET result_json = ?, edit_count = edit_count + 1 WHERE id = ?",
            (result.model_dump_json(), analysis_id),
        )


def list_history(limit: int, offset: int) -> tuple[list[dict], int]:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_row_to_record(r) for r in rows], total


def all_edited() -> list[dict]:
    """ผลทั้งหมดที่ผู้ใช้แก้แล้วอย่างน้อย 1 ครั้ง — ใช้ export ป้ายกำกับ"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE edit_count > 0 ORDER BY created_at"
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def stats() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT timings_json, edit_count FROM analyses").fetchall()
    n = len(rows)
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    total_edits = 0
    for r in rows:
        total_edits += r["edit_count"]
        for stage, seconds in json.loads(r["timings_json"]).items():
            sums[stage] = sums.get(stage, 0.0) + seconds
            counts[stage] = counts.get(stage, 0) + 1
    avg_timings = {stage: round(sums[stage] / counts[stage], 4) for stage in sums}
    return {
        "analyses_count": n,
        "avg_timings_sec": avg_timings,
        "total_edits": total_edits,
        "edits_per_analysis_avg": round(total_edits / n, 2) if n else 0.0,
    }
