"""ส่วนที่ 2: หาตำแหน่งเหรียญ"""

from schemas import COIN_TYPES, Coin, PreprocessResult


def detect_coins(pre: PreprocessResult) -> list[Coin]:
    """คืนเหรียญที่มี center_xy / radius_px / ellipse (พิกัดภาพหลัง preprocess) ยังไม่มี color_group / coin_type

    TODO(ส่วนที่ 2): threshold/K-Means/Canny → morphology → watershed → fit ellipse → กรองความกลม
    """
    raise NotImplementedError("detect_coins ยังไม่เสร็จ ใช้ mock_detect_coins ไปก่อน")


def mock_detect_coins(pre: PreprocessResult) -> list[Coin]:
    """วางเหรียญทุกชนิดเรียงเป็นแถวกลางภาพ รัศมีเป็นสัดส่วนกับขนาดจริง"""
    h, w = pre.gray.shape[:2]
    step = w / (len(COIN_TYPES) + 1)
    px_per_mm = step * 0.8 / max(t.diameter_mm for t in COIN_TYPES)
    return [
        Coin(coin_id=i, center_xy=(step * (i + 1), h / 2), radius_px=t.diameter_mm * px_per_mm / 2)
        for i, t in enumerate(COIN_TYPES)
    ]
