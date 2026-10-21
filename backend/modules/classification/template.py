"""ยืนยันชนิดเหรียญจากลวดลายด้วย template matching (W7 geometric transform + W8 template matching)

ขั้นตอนต่อเหรียญ
1. ตัดภาพเหรียญแล้ว warp affine ให้วงรี (ภาพเอียง) กลายเป็นวงกลมรัศมีมาตรฐาน NORM_RADIUS
2. ขนาดเกรเดียนต์ Sobel (ทนต่อความสว่างต่างกันมากกว่าค่าเทาโดยตรง)
3. แปลงเป็นพิกัดเชิงขั้ว (warpPolar): การหมุนเหรียญกลายเป็นการเลื่อนตามแกนมุม
4. normalized cross-correlation กับ template ทุกมุมพร้อมกันด้วย FFT ตามแกนมุม แล้วใช้ค่าสูงสุด

ใช้แก้กรณีสเกลไม่ชัด (เช่น เหรียญเงินขนาดเดียวทั้งภาพ): ถ้าลวดลายบอกชนิดได้ชัด ใช้เหรียญนั้นเป็น anchor แทนการถามผู้ใช้
template สร้างจากเหรียญที่มีป้ายกำกับในชุดปรับระบบ (build_templates) โมดูลนี้ไม่อ่านไฟล์เอง
"""
from __future__ import annotations

import cv2
import numpy as np

from schemas import Coin

NORM_RADIUS = 48                 # รัศมีเหรียญหลังปรับขนาด (px)
N_ANGLES = 128                   # จำนวนมุมในภาพเชิงขั้ว
RADIAL_RANGE = (0.15, 0.85)      # ใช้เฉพาะช่วงรัศมีนี้ (ตัดจุดกลางที่บิดมากและขอบที่มีเงา/พื้นหลังปน)

MIN_SCORE = 0.30                 # คะแนนของชนิดที่ดีที่สุดต้องไม่ต่ำกว่านี้
MIN_MARGIN = 0.08                # และต้องห่างจากชนิดอันดับสองอย่างน้อยเท่านี้

Templates = dict[str, list[np.ndarray]]   # รหัสเหรียญ -> ลักษณะเชิงขั้วของแต่ละ template (หลายด้าน/หลายเหรียญ)


def _normalize(gray: np.ndarray, center: tuple[float, float], major: float, minor: float,
               angle_deg: float) -> np.ndarray:
    """warp วงรีของเหรียญให้เป็นวงกลมรัศมี NORM_RADIUS กลางภาพขนาด 2*NORM_RADIUS"""
    size = 2 * NORM_RADIUS
    k = (major / 2) / NORM_RADIUS
    if k > 1.5:
        # ย่อภาพมาก เบลอก่อนกัน aliasing
        gray = cv2.GaussianBlur(gray, (0, 0), sigmaX=0.5 * k)
    th = np.deg2rad(angle_deg)
    rot = np.array([[np.cos(th), np.sin(th)], [-np.sin(th), np.cos(th)]])   # หมุนให้แกนยาวอยู่แนวนอน
    scale = np.diag([NORM_RADIUS / (major / 2), NORM_RADIUS / (minor / 2)])
    a = scale @ rot
    t = np.array([NORM_RADIUS, NORM_RADIUS]) - a @ np.asarray(center, dtype=float)
    m = np.hstack([a, t[:, None]]).astype(np.float32)
    return cv2.warpAffine(gray, m, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _polar_feature(norm: np.ndarray) -> np.ndarray | None:
    img = norm.astype(np.float32)
    gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    polar = cv2.warpPolar(mag, (NORM_RADIUS, N_ANGLES), (NORM_RADIUS, NORM_RADIUS), NORM_RADIUS,
                          cv2.WARP_POLAR_LINEAR | cv2.INTER_LINEAR)   # แถว = มุม, คอลัมน์ = รัศมี
    r0, r1 = (int(f * NORM_RADIUS) for f in RADIAL_RANGE)
    feat = polar[:, r0:r1]
    feat = feat - feat.mean()
    norm_ = np.linalg.norm(feat)
    if norm_ < 1e-6:
        return None      # ไม่มีลวดลาย (เรียบสนิท)
    return feat / norm_


def coin_features(gray: np.ndarray, coin: Coin) -> list[np.ndarray]:
    """ลักษณะเชิงขั้วของเหรียญ ภาพเอียงคืน 2 แบบ (มุมของแกนยาวกำกวม 90°) ใช้ค่าที่ match ดีกว่า"""
    if coin.ellipse is not None and coin.ellipse[1] > 0:
        major, minor, angle = coin.ellipse
        angles = [angle, angle + 90.0] if minor < major * 0.98 else [0.0]
    else:
        major = minor = 2 * coin.radius_px
        angles = [0.0]
    feats = [_polar_feature(_normalize(gray, coin.center_xy, major, minor, a)) for a in angles]
    return [f for f in feats if f is not None]


def _ncc_max(a: np.ndarray, b: np.ndarray) -> float:
    """NCC สูงสุดเมื่อเลื่อน b ทุกมุม (FFT ตามแกนมุม รวมทุกรัศมี)"""
    fa = np.fft.rfft(a, axis=0)
    fb = np.fft.rfft(b, axis=0)
    corr = np.fft.irfft((fa * np.conj(fb)).sum(axis=1), n=a.shape[0])
    return float(corr.max())


def build_templates(samples: list[tuple[np.ndarray, Coin, str]]) -> Templates:
    """samples = (ภาพเทา, เหรียญ, รหัสชนิดจริง) จากชุดปรับระบบ"""
    out: Templates = {}
    for gray, coin, code in samples:
        feats = coin_features(gray, coin)
        if feats:
            out.setdefault(code, []).append(feats[0])
    return out


def match_scores(gray: np.ndarray, coin: Coin, templates: Templates, codes: list[str]) -> dict[str, float]:
    """คะแนนสูงสุดต่อชนิด (เฉพาะชนิดใน codes ที่มี template)"""
    feats = coin_features(gray, coin)
    if not feats:
        return {}
    return {
        code: max(_ncc_max(f, t) for f in feats for t in templates[code])
        for code in codes if templates.get(code)
    }


def decide(scores: dict[str, float]) -> tuple[str, float] | None:
    """(ชนิด, ระยะห่างจากอันดับสอง) ถ้าลวดลายบอกชนิดได้ชัด ไม่งั้น None"""
    if len(scores) < 2:
        return None
    (c1, s1), (_, s2) = sorted(scores.items(), key=lambda kv: -kv[1])[:2]
    if s1 < MIN_SCORE or s1 - s2 < MIN_MARGIN:
        return None
    return c1, s1 - s2
