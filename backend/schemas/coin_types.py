"""ตารางชนิดเหรียญ (หัวข้อ 0 ในแผน) — ส่วนที่ 1 ยืนยันขนาดด้วยเวอร์เนียในสัปดาห์ 1"""

from .models import CoinTypeInfo

COIN_TYPES: list[CoinTypeInfo] = [
    CoinTypeInfo(code="THB_0_25", name_th="25 สตางค์", value_baht=0.25, diameter_mm=16.0, color_group="copper", display_color="#b45309"),
    CoinTypeInfo(code="THB_0_50", name_th="50 สตางค์", value_baht=0.50, diameter_mm=18.0, color_group="copper", display_color="#ea580c"),
    CoinTypeInfo(code="THB_1", name_th="1 บาท", value_baht=1.0, diameter_mm=20.0, color_group="silver", display_color="#64748b"),
    CoinTypeInfo(code="THB_2", name_th="2 บาท", value_baht=2.0, diameter_mm=21.75, color_group="gold", display_color="#ca8a04"),
    CoinTypeInfo(code="THB_5", name_th="5 บาท", value_baht=5.0, diameter_mm=24.0, color_group="silver", display_color="#2563eb"),
    CoinTypeInfo(code="THB_10", name_th="10 บาท", value_baht=10.0, diameter_mm=26.0, color_group="bimetal", display_color="#16a34a"),
]

COIN_TYPES_BY_CODE: dict[str, CoinTypeInfo] = {t.code: t for t in COIN_TYPES}
