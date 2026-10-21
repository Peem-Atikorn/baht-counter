"""ภาพกลางทางสำหรับหน้า "เกี่ยวกับ" (คืนเป็น ndarray ให้ส่วนที่ 4 เข้ารหัสและเก็บเอง)"""
from __future__ import annotations

import cv2
import numpy as np

from schemas import CountResult

from .coin_specs import COIN_SPECS

GROUP_COLORS_BGR = {
    "copper": (40, 90, 200),
    "silver": (200, 200, 200),
    "gold": (0, 200, 255),
    "bimetal": (255, 120, 0),
    "unknown": (0, 0, 255),
}


def draw_color_groups(image_bgr: np.ndarray, result: CountResult) -> np.ndarray:
    """วงกลมสีตามกลุ่มสี + ป้ายชนิดเหรียญ"""
    out = image_bgr.copy()
    thick = max(2, round(max(out.shape[:2]) / 500))
    for c in result.coins:
        center = (round(c.center_xy[0]), round(c.center_xy[1]))
        cv2.circle(out, center, round(c.radius_px), GROUP_COLORS_BGR[c.color_group], thick)
        label = c.coin_type if c.coin_type in COIN_SPECS else "?"
        cv2.putText(out, label.replace("THB_", ""), (center[0] - 15, center[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4 * thick, (0, 0, 0), thick + 2)
        cv2.putText(out, label.replace("THB_", ""), (center[0] - 15, center[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4 * thick, (255, 255, 255), thick)
    return out
