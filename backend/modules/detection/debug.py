"""การสร้างภาพกลางทาง (Debug Images) สำหรับหน้า 'เกี่ยวกับ' และการตรวจสอบผล"""

from __future__ import annotations

import cv2
import numpy as np

from schemas import Coin


def render_distance_map(dist: np.ndarray) -> np.ndarray:
    """แปลง Distance Transform เป็นภาพ Heatmap สีสันสดใส (BGR) ด้วย Colormap JET"""
    if dist.max() > 0:
        dist_norm = (dist / dist.max() * 255.0).astype(np.uint8)
    else:
        dist_norm = np.zeros_like(dist, dtype=np.uint8)
    return cv2.applyColorMap(dist_norm, cv2.COLORMAP_JET)


def render_watershed_map(markers: np.ndarray) -> np.ndarray:
    """แปลง Watershed Markers เป็นภาพสีแยกตามเหรียญ และไฮไลต์ขอบเขตสีแดง (-1)"""
    h, w = markers.shape[:2]
    vis = np.zeros((h, w, 3), dtype=np.uint8)

    unique_labels = np.unique(markers)
    # สุ่มสีที่คงที่สำหรับแต่ละ label โดยใช้ random seed
    rng = np.random.default_rng(42)
    colors = {
        lbl: rng.integers(50, 240, size=3, dtype=np.uint8).tolist()
        for lbl in unique_labels
        if lbl >= 2
    }
    colors[1] = [30, 30, 30]  # สีพื้นหลัง: เทาเข้ม

    for lbl, color in colors.items():
        vis[markers == lbl] = color

    # ขอบเขตที่ watershed ตัด (-1) ให้เป็นสีแดงสด
    vis[markers == -1] = [0, 0, 255]
    return vis


def render_detection_overlay(image: np.ndarray, coins: list[Coin]) -> np.ndarray:
    """วาดวงรี/วงกลม และจุดศูนย์กลางทับลงบนภาพต้นฉบับ"""
    vis = image.copy()
    for coin in coins:
        cx, cy = int(round(coin.center_xy[0])), int(round(coin.center_xy[1]))
        r = int(round(coin.radius_px))

        if coin.ellipse is not None:
            major, minor, angle = coin.ellipse
            axes = (int(round(major / 2.0)), int(round(minor / 2.0)))
            cv2.ellipse(vis, (cx, cy), axes, angle, 0, 360, (0, 255, 0), 2)
        else:
            cv2.circle(vis, (cx, cy), r, (0, 255, 0), 2)

        # จุดศูนย์กลาง (Crosshair)
        cv2.drawMarker(vis, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 10, 2)
        # ป้ายกำกับ ID
        cv2.putText(
            vis,
            f"#{coin.coin_id}",
            (cx - 15, cy - r - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )

    return vis
