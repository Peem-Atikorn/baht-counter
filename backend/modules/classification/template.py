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
MIN_RADIUS_PX = 4.0              # เหรียญรัศมี (แกนสั้น) เล็กกว่านี้ไม่ใช้ลวดลาย

MIN_SCORE = 0.30                 # คะแนนของชนิดที่ดีที่สุดต้องไม่ต่ำกว่านี้
MIN_MARGIN = 0.08                # และต้องห่างจากชนิดอันดับสองอย่างน้อยเท่านี้

Templates = dict[str, list[np.ndarray]]   # รหัสเหรียญ -> สเปกตรัม (rfft ตามแกนมุม) ของแต่ละ template (หลายด้าน/หลายเหรียญ)


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


def _gradient(img: np.ndarray) -> np.ndarray:
    img = img.astype(np.float32)
    return cv2.magnitude(cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=3))


def _polar_feature(norm: np.ndarray) -> np.ndarray | None:
    polar = cv2.warpPolar(_gradient(norm), (NORM_RADIUS, N_ANGLES), (NORM_RADIUS, NORM_RADIUS), NORM_RADIUS,
                          cv2.WARP_POLAR_LINEAR | cv2.INTER_LINEAR)   # แถว = มุม, คอลัมน์ = รัศมี
    r0, r1 = (int(f * NORM_RADIUS) for f in RADIAL_RANGE)
    feat = polar[:, r0:r1]
    feat = feat - feat.mean()
    norm_ = np.linalg.norm(feat)
    if norm_ < 1e-6:
        return None      # ไม่มีลวดลาย (เรียบสนิท)
    return feat / norm_


def _rim_strength(gray: np.ndarray, center: tuple[float, float], major: float, minor: float,
                  angle_deg: float) -> float:
    """เกรเดียนต์เฉลี่ยบนเส้นรอบวงรี ถ้าแกนยาวอยู่ที่มุม angle_deg จริง เส้นจะทับขอบเหรียญตลอดวง"""
    cx, cy = center
    pad = major / 2 + 3
    x0, y0 = max(0, int(cx - pad)), max(0, int(cy - pad))
    crop = gray[y0:int(cy + pad) + 1, x0:int(cx + pad) + 1]
    if crop.size == 0:
        return 0.0
    mag = _gradient(crop)
    t = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    th = np.deg2rad(angle_deg)
    a, b = major / 2 * np.cos(t), minor / 2 * np.sin(t)
    xs = np.clip(np.rint(cx + a * np.cos(th) - b * np.sin(th) - x0).astype(int), 0, mag.shape[1] - 1)
    ys = np.clip(np.rint(cy + a * np.sin(th) + b * np.cos(th) - y0).astype(int), 0, mag.shape[0] - 1)
    return float(mag[ys, xs].mean())


def _orientations(gray: np.ndarray, coin: Coin) -> list[tuple[np.ndarray | None, float]]:
    """(ลักษณะเชิงขั้ว, ความแรงขอบ) ของแต่ละแบบที่ warp ได้ ภาพเอียงมี 2 แบบ (มุมของแกนยาวกำกวม 90°)"""
    if coin.ellipse is not None and coin.ellipse[1] > 0:
        major, minor, angle = coin.ellipse
        angles = [angle, angle + 90.0] if minor < major * 0.98 else [0.0]
    else:
        major = minor = 2 * coin.radius_px
        angles = [0.0]
    if minor < MIN_RADIUS_PX * 2:
        return []        # เล็กเกินกว่าจะเห็นลวดลาย (และกันหารด้วย 0)
    return [(_polar_feature(_normalize(gray, coin.center_xy, major, minor, a)),
             _rim_strength(gray, coin.center_xy, major, minor, a) if len(angles) > 1 else 0.0)
            for a in angles]


def coin_feature(gray: np.ndarray, coin: Coin) -> np.ndarray | None:
    """ลักษณะเชิงขั้วของเหรียญ ภาพเอียงเลือกแกนที่ขอบเป็นวงกลมพอดี (ellipse จาก detection เรียงแกนยาว/สั้นใหม่
    แต่ angle อาจเป็นของแกนสั้น) ใช้ทั้งตอนสร้าง template และตอนจำแนก แบบที่ยืดผิดแกนอาจบังเอิญคล้ายอีกชนิด"""
    opts = [o for o in _orientations(gray, coin) if o[0] is not None]
    return max(opts, key=lambda o: o[1])[0] if opts else None


def _spectrum(feat: np.ndarray) -> np.ndarray:
    return np.fft.rfft(feat, axis=0)


def _ncc_spec(fa: np.ndarray, fb: np.ndarray) -> float:
    """NCC สูงสุดเมื่อเลื่อนทุกมุม จากสเปกตรัมตามแกนมุม (รวมทุกรัศมี)"""
    return float(np.fft.irfft((fa * np.conj(fb)).sum(axis=1), n=N_ANGLES).max())


def _ncc_max(a: np.ndarray, b: np.ndarray) -> float:
    """NCC สูงสุดเมื่อเลื่อน b ทุกมุม จากลักษณะเชิงขั้วโดยตรง"""
    return _ncc_spec(_spectrum(a), _spectrum(b))


def build_templates(samples: list[tuple[np.ndarray, Coin, str]]) -> Templates:
    """samples = (ภาพเทา, เหรียญ, รหัสชนิดจริง) จากชุดปรับระบบ เก็บเป็นสเปกตรัมไว้เลย ไม่ต้อง FFT ใหม่ทุกครั้งที่จำแนก"""
    out: Templates = {}
    for gray, coin, code in samples:
        f = coin_feature(gray, coin)
        if f is not None:
            out.setdefault(code, []).append(_spectrum(f))
    return out


def match_scores(gray: np.ndarray, coin: Coin, templates: Templates, codes: list[str]) -> dict[str, float]:
    """คะแนนสูงสุดต่อชนิด (เฉพาะชนิดใน codes ที่มี template)"""
    f = coin_feature(gray, coin)
    if f is None:
        return {}
    fs = _spectrum(f)
    return {code: max(_ncc_spec(fs, t) for t in templates[code]) for code in codes if templates.get(code)}


def decide(scores: dict[str, float]) -> tuple[str, float] | None:
    """(ชนิด, ระยะห่างจากอันดับสอง) ถ้าลวดลายบอกชนิดได้ชัด ไม่งั้น None"""
    if len(scores) < 2:
        return None
    (c1, s1), (_, s2) = sorted(scores.items(), key=lambda kv: -kv[1])[:2]
    if s1 < MIN_SCORE or s1 - s2 < MIN_MARGIN:
        return None
    return c1, s1 - s2
