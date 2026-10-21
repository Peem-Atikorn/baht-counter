"""ข้อมูลเหรียญ ใช้ตารางจาก schema กลาง (docs/plan.md หัวข้อ 0)"""
from schemas import COIN_TYPES, COIN_TYPES_BY_CODE

COIN_SPECS = COIN_TYPES_BY_CODE
COIN_CODES: list[str] = [t.code for t in COIN_TYPES]

# กลุ่มสีจำกัดชนิดที่เป็นไปได้ ถ้าไม่รู้สีให้เป็นได้ทุกชนิด
GROUP_TYPES: dict[str, list[str]] = {
    g: [t.code for t in COIN_TYPES if t.color_group == g]
    for g in ("copper", "silver", "gold", "bimetal")
}
GROUP_TYPES["unknown"] = COIN_CODES
