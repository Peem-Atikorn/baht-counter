"""การแยกเหรียญที่ชิดหรือสัมผัสกันด้วย Distance Transform และ Watershed Algorithm"""

from __future__ import annotations

import cv2
import numpy as np


def find_coin_markers(
    mask: np.ndarray,
    dist: np.ndarray,
    min_distance_px: float = 8.0,
    peak_kernel_size: int = 15,
) -> tuple[int, np.ndarray]:
    """ค้นหาจุดศูนย์กลางเหรียญ (Local Maxima / Seeds) สำหรับเป็น Markers ของ Watershed"""
    if dist.max() <= 0:
        return 0, np.zeros_like(mask, dtype=np.int32)

    # 1. Local Maxima Detection: พิกเซลที่เป็นยอดสูงสุดในรัศมีรอบข้าง
    ksize = max(5, peak_kernel_size if peak_kernel_size % 2 == 1 else peak_kernel_size + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    dilated_dist = cv2.dilate(dist, kernel)

    local_peaks = (dist == dilated_dist) & (dist >= min_distance_px)

    # 2. ป้องกันเหรียญขนาดเล็กหลุดรอด: วิเคราะห์ราย Connected Component ใน mask
    num_comps, comp_labels = cv2.connectedComponents(mask)
    sure_fg = np.zeros_like(mask, dtype=bool)

    for comp_idx in range(1, num_comps):
        comp_mask = (comp_labels == comp_idx)
        comp_dist_max = float(np.max(dist[comp_mask]))
        if comp_dist_max < min_distance_px:
            continue

        comp_peaks = local_peaks & comp_mask
        if np.any(comp_peaks):
            sure_fg |= comp_peaks
        else:
            sure_fg |= (dist >= (0.60 * comp_dist_max)) & comp_mask

    # 3. รวมยอด plateau ที่ติดกัน
    sure_fg_u8 = sure_fg.astype(np.uint8) * 255
    merge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    sure_fg_u8 = cv2.morphologyEx(sure_fg_u8, cv2.MORPH_CLOSE, merge_kernel)

    num_markers, markers = cv2.connectedComponents(sure_fg_u8)
    return num_markers, markers


def apply_watershed(
    image: np.ndarray,
    mask: np.ndarray,
    min_distance_px: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """คำนวณ Distance Transform และรัน Watershed Segmentation แบบ Component-Guided

    - เหรียญเดี่ยว (Component ที่มี 1 marker): รักษาขอบเขตสมบูรณ์ ไม่ถูกรบกวนด้วยขอบเขตภายในเหรียญ (เช่น เหรียญสองสี 10 บาท)
    - เหรียญชิดกัน (Component ที่มี >= 2 markers): รัน Watershed ตัดแบ่งตามแนวรอยต่อ
    - min_distance_px ปรับตามขนาดของภาพอัตโนมัติหากไม่ได้ระบุ
    """
    h, w = mask.shape[:2]
    if min_distance_px is None:
        min_distance_px = max(5.0, min(h, w) * 0.008)

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    if dist.max() < min_distance_px:
        return np.ones_like(mask, dtype=np.int32), dist

    num_markers, fg_markers = find_coin_markers(mask, dist, min_distance_px=min_distance_px)
    if num_markers <= 1:
        return np.ones_like(mask, dtype=np.int32), dist

    num_comps, comp_labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    final_markers = np.ones_like(mask, dtype=np.int32)  # 1 = พื้นหลัง
    next_label = 2

    img_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if len(image.shape) == 2 else image
    dilate_kernel = np.ones((7, 7), np.uint8)

    for c_idx in range(1, num_comps):
        x, y, cw, ch, area = stats[c_idx]
        pad = 15
        y1, y2 = max(0, y - pad), min(h, y + ch + pad)
        x1, x2 = max(0, x - pad), min(w, x + cw + pad)

        sub_comp = comp_labels[y1:y2, x1:x2]
        sub_c_mask = (sub_comp == c_idx)
        sub_fg_markers = fg_markers[y1:y2, x1:x2]

        markers_in_c = np.unique(sub_fg_markers[sub_c_mask])
        markers_in_c = markers_in_c[markers_in_c > 0]

        if len(markers_in_c) <= 1:
            # เหรียญเดี่ยว: กำหนด label ได้ทันทีโดยไม่ต้องรัน watershed
            final_markers[y1:y2, x1:x2][sub_c_mask] = next_label
            next_label += 1
        else:
            # กลุ่มเหรียญชิดกัน: รัน watershed ตัดแบ่งขอบเขตเฉพาะภายใน ROI ของกลุ่มนี้ (เร็วกว่ารันทั้งภาพ ~2x)
            sub_sure_bg = cv2.dilate(sub_c_mask.astype(np.uint8) * 255, dilate_kernel, iterations=2)
            sub_w_markers = np.zeros((y2 - y1, x2 - x1), dtype=np.int32)
            cluster_start_label = next_label
            for m_id in markers_in_c:
                sub_w_markers[sub_c_mask & (sub_fg_markers == m_id)] = next_label
                next_label += 1

            sub_w_markers[sub_sure_bg == 0] = 1  # ภายนอกกลุ่มเป็นพื้นหลัง
            sub_unknown = (sub_sure_bg > 0) & (sub_w_markers == 0)
            sub_w_markers[sub_unknown] = 0

            sub_img_bgr = img_bgr[y1:y2, x1:x2]
            cv2.watershed(sub_img_bgr, sub_w_markers)

            sub_final = final_markers[y1:y2, x1:x2]
            for lbl in range(cluster_start_label, next_label):
                sub_final[sub_w_markers == lbl] = lbl

    return final_markers, dist
