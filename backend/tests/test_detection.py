"""ชุดทดสอบสำหรับโมดูลส่วนที่ 2: หาตำแหน่งเหรียญ (Detection)"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from modules.detection import (
    detect_coin_at,
    detect_coins,
    detect_coins_hough,
    detect_coins_kmeans,
    detect_coins_no_watershed,
    mock_detect_coins,
)
from schemas import COIN_TYPES, Coin, PreprocessResult


def make_test_pre(
    image: np.ndarray,
    status: str = "ok",
) -> PreprocessResult:
    """Helper สำหรับแปลงภาพ numpy เป็น PreprocessResult สำหรับทดสอบ"""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return PreprocessResult(
        image=image,
        gray=gray,
        resize_factor=1.0,
        original_size=(w, h),
        status=status,
        debug_images={},
    )


def test_mock_detect_coins():
    """Mock detection ยังคงทำงานได้ถูกต้องตามสัญญากลาง"""
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    pre = make_test_pre(img)
    coins = mock_detect_coins(pre)

    assert len(coins) == len(COIN_TYPES)
    for c in coins:
        assert isinstance(c, Coin)
        assert c.radius_px > 0
        assert 0 <= c.center_xy[0] <= 800
        assert 0 <= c.center_xy[1] <= 600


def test_detect_single_coin():
    """ตรวจจับเหรียญเดี่ยว 1 เหรียญ ความคลาดเคลื่อนของจุดศูนย์กลาง < 2px และรัศมี < 3%"""
    h, w = 400, 400
    img = np.full((h, w, 3), 40, dtype=np.uint8)  # พื้นหลังสีเข้ม (40)
    true_center = (200.0, 200.0)
    true_radius = 60.0

    # วาดเหรียญสีเงิน (180) พร้อมจุดแสงสะท้อน (glare) สีขาว
    cv2.circle(img, (int(true_center[0]), int(true_center[1])), int(true_radius), (180, 180, 180), -1)
    cv2.circle(img, (185, 185), 10, (255, 255, 255), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    assert len(coins) == 1
    c = coins[0]

    # ตรวจสอบจุดศูนย์กลาง: ห่างไม่เกิน 2 พิกเซล
    dist = np.hypot(c.center_xy[0] - true_center[0], c.center_xy[1] - true_center[1])
    assert dist <= 2.0

    # ตรวจสอบรัศมี: คลาดเคลื่อนไม่เกิน 3%
    radius_error_pct = abs(c.radius_px - true_radius) / true_radius * 100.0
    assert radius_error_pct <= 3.0


def test_detect_single_coin_on_light_background():
    """ตรวจจับเหรียญบนพื้นหลังสีสว่าง (กระดาษขาว) ได้ถูกต้อง"""
    h, w = 400, 400
    img = np.full((h, w, 3), 245, dtype=np.uint8)  # พื้นหลังสีขาว
    true_center = (200.0, 200.0)
    true_radius = 50.0

    # วาดเหรียญสีทองแดง/ทอง (เข้มกว่ากระดาษ)
    cv2.circle(img, (int(true_center[0]), int(true_center[1])), int(true_radius), (60, 100, 180), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    assert len(coins) == 1
    c = coins[0]
    dist = np.hypot(c.center_xy[0] - true_center[0], c.center_xy[1] - true_center[1])
    assert dist <= 2.0
    assert abs(c.radius_px - true_radius) / true_radius <= 0.03


def test_detect_multiple_coins_separated():
    """ตรวจจับเหรียญหลายเหรียญที่มีขนาดต่างกันได้อย่างครบถ้วน"""
    h, w = 400, 800
    img = np.full((h, w, 3), 120, dtype=np.uint8)

    ground_truth = [
        ((150.0, 200.0), 65.0),  # เหรียญใหญ่ (10 บาท)
        ((350.0, 200.0), 50.0),  # เหรียญกลาง (1 บาท)
        ((550.0, 200.0), 40.0),  # เหรียญเล็ก (25 สตางค์)
    ]

    for (cx, cy), r in ground_truth:
        cv2.circle(img, (int(cx), int(cy)), int(r), (200, 200, 200), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    assert len(coins) == 3
    # ตรวจสอบการจับคู่แต่ละเหรียญ
    for (gcx, gcy), gr in ground_truth:
        matched = [c for c in coins if np.hypot(c.center_xy[0] - gcx, c.center_xy[1] - gcy) <= 3.0]
        assert len(matched) == 1
        c = matched[0]
        assert abs(c.radius_px - gr) / gr <= 0.03


def test_detect_touching_coins_watershed():
    """Watershed สามารถแยกเหรียญ 2 เหรียญที่วางสัมผัสชิดกันได้ ขณะที่แบบไม่ใช้ Watershed จะรวมเป็นก้อนเดียว"""
    h, w = 400, 600
    img = np.full((h, w, 3), 30, dtype=np.uint8)

    r1, r2 = 50.0, 50.0
    c1 = (200.0, 200.0)
    # วางให้สัมผัสชิดกันพอดี (ระยะห่างจุดศูนย์กลาง = r1 + r2)
    c2 = (c1[0] + r1 + r2, 200.0)

    cv2.circle(img, (int(c1[0]), int(c1[1])), int(r1), (210, 210, 210), -1)
    cv2.circle(img, (int(c2[0]), int(c2[1])), int(r2), (210, 210, 210), -1)

    pre = make_test_pre(img)

    # 1. รันด้วย detect_coins (ใช้ Watershed) ต้องได้ 2 เหรียญ
    coins_watershed = detect_coins(pre)
    assert len(coins_watershed) == 2, f"Watershed ควรแยกได้ 2 เหรียญ แต่ได้ {len(coins_watershed)}"

    # 2. รันด้วย detect_coins_no_watershed (ไม่ใช้ Watershed)
    coins_no_watershed = detect_coins_no_watershed(pre)
    # วัตถุที่เชื่อมติดกันจะกลายเป็น 1 ชิ้น ซึ่งอาจตกเกณฑ์ Circularity หรือกลายเป็น 1 ก้อนใหญ่
    assert len(coins_no_watershed) <= 1


def test_fit_ellipse_tilted_coin():
    """ภาพเหรียญที่ถ่ายมุมเอียง (วงรี) รัศมีต้องวัดจากแกนยาว (Semi-major Axis)"""
    h, w = 500, 500
    img = np.full((h, w, 3), 40, dtype=np.uint8)

    cx, cy = 250.0, 250.0
    major_axis = 120.0  # เส้นผ่านศูนย์กลางจริง = 120 px (รัศมี = 60 px)
    minor_axis = 104.0  # มุมเอียง ~30 องศา cos(30) ~ 0.866
    angle = 45.0

    axes = (int(round(major_axis / 2.0)), int(round(minor_axis / 2.0)))
    cv2.ellipse(img, (int(cx), int(cy)), axes, angle, 0, 360, (200, 200, 200), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    assert len(coins) == 1
    c = coins[0]
    assert c.ellipse is not None
    # รัศมีต้องเป็นครึ่งหนึ่งของแกนยาว
    assert abs(c.radius_px - (major_axis / 2.0)) <= 2.0
    # แกนยาวและแกนสั้นใน ellipse ต้องใกล้เคียงค่าจริง
    maj, mino, ang = c.ellipse
    assert abs(maj - major_axis) <= 3.0
    assert abs(mino - minor_axis) <= 3.0


def test_circularity_filter_rejects_non_coins():
    """วัตถุที่ไม่ใช่ทรงกลม/วงรี (เช่น แถบสี่เหลี่ยมยาว หรือปากกา) ต้องถูกกรองทิ้ง"""
    h, w = 400, 400
    img = np.full((h, w, 3), 40, dtype=np.uint8)

    # วาดแถบสี่เหลี่ยมยาว 200x20 px (Aspect ratio 10:1, Circularity ต่ำมาก)
    cv2.rectangle(img, (100, 190), (300, 210), (200, 200, 200), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    # ต้องไม่ถูกระบุว่าเป็นเหรียญ
    assert len(coins) == 0


def test_detect_coin_at_click():
    """ฟังก์ชัน detect_coin_at ทำงานถูกต้องเมื่อผู้ใช้กดบนภาพ"""
    h, w = 400, 400
    img = np.full((h, w, 3), 50, dtype=np.uint8)
    cx, cy, r = 200.0, 200.0, 50.0
    cv2.circle(img, (int(cx), int(cy)), int(r), (190, 190, 190), -1)

    pre = make_test_pre(img)

    # 1. กดภายในขอบเขตเหรียญ
    clicked_coin = detect_coin_at(pre, (210.0, 195.0))
    assert clicked_coin is not None
    assert np.hypot(clicked_coin.center_xy[0] - cx, clicked_coin.center_xy[1] - cy) <= 2.0
    assert abs(clicked_coin.radius_px - r) <= 2.0

    # 2. กดบนพื้นหลังว่างเปล่า
    bg_click = detect_coin_at(pre, (50.0, 50.0))
    assert bg_click is None

    # 3. พิกัดนอกกรอบภาพ
    assert detect_coin_at(pre, (-10.0, 50.0)) is None
    assert detect_coin_at(pre, (500.0, 50.0)) is None


def test_debug_images_produced():
    """โมดูลต้องบันทึกภาพกลางทางลง pre.debug_images สำหรับหน้า 'เกี่ยวกับ'"""
    h, w = 300, 300
    img = np.full((h, w, 3), 50, dtype=np.uint8)
    cv2.circle(img, (150, 150), 40, (200, 200, 200), -1)

    pre = make_test_pre(img)
    detect_coins(pre)

    expected_keys = {
        "detection_edges",
        "detection_mask",
        "detection_distance",
        "detection_watershed",
        "detection_result",
    }
    assert expected_keys.issubset(set(pre.debug_images.keys()))
    for key in expected_keys:
        val = pre.debug_images[key]
        assert isinstance(val, np.ndarray)
        assert val.shape[:2] == (h, w)


def test_baselines_execute():
    """อัลกอริทึม Baseline (Hough, K-Means, Non-watershed) รันได้และคืน list[Coin]"""
    h, w = 300, 300
    img = np.full((h, w, 3), 50, dtype=np.uint8)
    cv2.circle(img, (150, 150), 45, (200, 200, 200), -1)
    pre = make_test_pre(img)

    hough_coins = detect_coins_hough(pre)
    assert len(hough_coins) >= 1
    assert abs(hough_coins[0].radius_px - 45.0) <= 5.0

    kmeans_coins = detect_coins_kmeans(pre)
    assert len(kmeans_coins) == 1
    assert abs(kmeans_coins[0].radius_px - 45.0) <= 2.0

    no_ws_coins = detect_coins_no_watershed(pre)
    assert len(no_ws_coins) == 1


def test_detect_touching_coins_different_sizes():
    """Watershed แยกเหรียญที่ชิดกันและมีขนาดต่างกันมากได้ (เช่น 10 บาท r=65 ชิดกับ 25 สตางค์ r=40)"""
    h, w = 400, 600
    img = np.full((h, w, 3), 40, dtype=np.uint8)

    c1, r1 = (200.0, 200.0), 65.0
    c2, r2 = (c1[0] + r1 + 40.0, 200.0), 40.0

    cv2.circle(img, (int(c1[0]), int(c1[1])), int(r1), (200, 200, 200), -1)
    cv2.circle(img, (int(c2[0]), int(c2[1])), int(r2), (200, 200, 200), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    assert len(coins) == 2
    # ตรวจจับทั้งเหรียญใหญ่และเหรียญเล็ก
    big = next(c for c in coins if c.radius_px > 50)
    small = next(c for c in coins if c.radius_px < 50)

    assert abs(big.radius_px - r1) / r1 <= 0.03
    assert abs(small.radius_px - r2) / r2 <= 0.03
    assert np.hypot(big.center_xy[0] - c1[0], big.center_xy[1] - c1[1]) <= 2.0
    assert np.hypot(small.center_xy[0] - c2[0], small.center_xy[1] - c2[1]) <= 2.0


def test_detect_all_synthetic_coin_types():
    """ทดสอบตรวจจับเหรียญทั้ง 6 ชนิดพร้อมกัน (รวม bimetal, copper, glare) จาก make_image"""
    from tests.test_classification import make_image

    types = ["THB_10", "THB_5", "THB_2", "THB_1", "THB_0_50", "THB_0_25"]
    pre, gt = make_image(types, seed=42)
    coins = detect_coins(pre)

    assert len(coins) == 6
    for g, p in zip(gt, coins):
        dist = np.hypot(g.center_xy[0] - p.center_xy[0], g.center_xy[1] - p.center_xy[1])
        assert dist <= 2.0
        # รัศมีคลาดเคลื่อนไม่เกิน 3%
        assert abs(g.radius_px - p.radius_px) / g.radius_px <= 0.03


def test_detect_uneven_illumination_gradient():
    """รีวิวข้อ 1: ภาพที่มีแสงไม่สม่ำเสมอ (ไล่ระดับ 90 ไป 150) ต้องหาเหรียญเจอครบทั้ง 2 เหรียญ"""
    from modules.preprocess import preprocess

    h, w = 1200, 1600
    grad_x = np.linspace(90, 150, w, dtype=np.float32)
    grad_img = np.tile(grad_x, (h, 1)).astype(np.uint8)
    img = cv2.cvtColor(grad_img, cv2.COLOR_GRAY2BGR)

    c1, r1 = (400.0, 600.0), 60.0
    c2, r2 = (1200.0, 600.0), 50.0
    cv2.circle(img, (int(c1[0]), int(c1[1])), int(r1), (180, 180, 180), -1)
    cv2.circle(img, (int(c2[0]), int(c2[1])), int(r2), (200, 200, 200), -1)

    # ทดสอบผ่าน preprocess จริง (ตามเงื่อนไขรีวิว)
    pre = preprocess(img)
    coins = detect_coins(pre)

    assert len(coins) == 2, f"ต้องตรวจพบ 2 เหรียญ แต่พบ {len(coins)} เหรียญ"
    coin1 = next(c for c in coins if c.center_xy[0] < 800)
    coin2 = next(c for c in coins if c.center_xy[0] >= 800)

    assert np.hypot(coin1.center_xy[0] - c1[0], coin1.center_xy[1] - c1[1]) <= 2.0
    assert np.hypot(coin2.center_xy[0] - c2[0], coin2.center_xy[1] - c2[1]) <= 2.0
    assert abs(coin1.radius_px - r1) / r1 <= 0.03
    assert abs(coin2.radius_px - r2) / r2 <= 0.03


def test_detect_coin_at_noise_background_returns_none():
    """รีวิวข้อ 2: กดบนพื้นหลังที่มีลาย noise (แทนโต๊ะไม้) ต้องคืน None ไม่สร้างเหรียญปลอม"""
    rng = np.random.default_rng(42)
    h, w = 800, 800
    noise = rng.normal(120, 20, (h, w)).astype(np.float32)
    blurred_noise = cv2.GaussianBlur(noise, (15, 15), 5).clip(0, 255).astype(np.uint8)
    img = cv2.cvtColor(blurred_noise, cv2.COLOR_GRAY2BGR)

    pre = make_test_pre(img)
    clicked = detect_coin_at(pre, (400.0, 400.0))
    assert clicked is None, "กดบนพื้นหลังลาย noise ต้องคืน None ห้ามสร้างเหรียญปลอม"


def test_filter_size_relative_to_coins():
    """รีวิวข้อ 6: กรองสิ่งแปลกปลอมขนาดผิดปกติเมื่อเทียบกับเหรียญอื่นในภาพ"""
    h, w = 600, 1200
    img = np.full((h, w, 3), 40, dtype=np.uint8)

    # เหรียญจริง 3 เหรียญ (r=50, 55, 60)
    cv2.circle(img, (200, 300), 50, (200, 200, 200), -1)
    cv2.circle(img, (400, 300), 55, (200, 200, 200), -1)
    cv2.circle(img, (600, 300), 60, (200, 200, 200), -1)

    # วัตถุแปลกปลอมกลมขนาดมหึมา (r=180 เกิน 2.2 เท่าของมัธยฐาน)
    cv2.circle(img, (950, 300), 180, (200, 200, 200), -1)

    pre = make_test_pre(img)
    coins = detect_coins(pre)

    # วัตถุ r=180 ต้องถูกกรองออก เหลือเฉพาะเหรียญจริง 3 เหรียญ
    assert len(coins) == 3
    assert all(c.radius_px < 100 for c in coins)


def test_detect_large_coin_uneven_illumination():
    """รีวิวรอบ 2 ข้อ 1: เหรียญใหญ่ r=150 และ r=220 บนพื้นที่แสงไล่ระดับ (80 ไป 160) ต้องได้รัศมีแม่นยำ (คลาดเคลื่อน < 1.5%)"""
    from modules.preprocess import preprocess

    h, w = 1200, 1600
    grad_x = np.linspace(80, 160, w, dtype=np.float32)
    grad_img = np.tile(grad_x, (h, 1)).astype(np.uint8)

    for target_r in [150.0, 220.0]:
        img = cv2.cvtColor(grad_img, cv2.COLOR_GRAY2BGR)
        cv2.circle(img, (800, 600), int(target_r), (210, 210, 210), -1)

        pre = preprocess(img)
        coins = detect_coins(pre)

        assert len(coins) == 1, f"ต้องตรวจพบ 1 เหรียญขนาดใหญ่ r={target_r}"
        coin = coins[0]
        # รัศมีคลาดเคลื่อนต้องไม่เกิน 1.5% (เกณฑ์ทีมคลาดเคลื่อนไม่เกิน 3%)
        r_error_pct = abs(coin.radius_px - target_r) / target_r * 100.0
        assert r_error_pct <= 1.5, f"r={target_r} แต่ตรวจได้ r={coin.radius_px:.1f} (error={r_error_pct:.2f}%)"
        assert np.hypot(coin.center_xy[0] - 800.0, coin.center_xy[1] - 600.0) <= 2.0


def test_detect_extreme_illumination_gradient():
    """รีวิวรอบ 2 ข้อ 2: พื้นหลังแสงไล่แรงมาก (60 ไป 200) เหรียญฝั่งสว่าง r=90 ต้องได้ค่าแม่นยำ"""
    from modules.preprocess import preprocess

    h, w = 1200, 1600
    grad_x = np.linspace(60, 200, w, dtype=np.float32)
    grad_img = np.tile(grad_x, (h, 1)).astype(np.uint8)
    img = cv2.cvtColor(grad_img, cv2.COLOR_GRAY2BGR)
    cv2.circle(img, (1300, 600), 90, (230, 230, 230), -1)

    pre = preprocess(img)
    coins = detect_coins(pre)

    assert len(coins) == 1
    coin = coins[0]
    assert abs(coin.radius_px - 90.0) / 90.0 <= 0.02
    assert np.hypot(coin.center_xy[0] - 1300.0, coin.center_xy[1] - 600.0) <= 2.0


def test_detect_coin_at_large_coin():
    """รีวิวรอบ 2 ข้อ 4: detect_coin_at รองรับเหรียญขนาดใหญ่ r=230px เมื่อผู้ใช้กดเพิ่มเหรียญ"""
    h, w = 1200, 1600
    img = np.full((h, w, 3), 50, dtype=np.uint8)
    cv2.circle(img, (600, 600), 230, (200, 200, 200), -1)

    pre = make_test_pre(img)
    clicked = detect_coin_at(pre, (610.0, 595.0))

    assert clicked is not None, "เหรียญใหญ่ r=230 ต้องสามารถตรวจจับได้เมื่อคลิก"
    assert abs(clicked.radius_px - 230.0) / 230.0 <= 0.02
    assert np.hypot(clicked.center_xy[0] - 600.0, clicked.center_xy[1] - 600.0) <= 3.0


def test_segment_bounded_fill_holes():
    """ทดสอบว่า fill_internal_holes แบบจำกัดขนาด ไม่เชื่อมรูขนาดใหญ่ที่เกิดจากพื้นหลังระหว่างเหรียญ"""
    from modules.detection.segment import fill_internal_holes

    mask = np.zeros((200, 200), dtype=np.uint8)
    # วาดกรอบสี่เหลี่ยมกลวงขนาดใหญ่
    cv2.rectangle(mask, (20, 20), (180, 180), 255, 10)
    # วาดวงกลมกลวงขนาดเล็ก (รูแสงสะท้อนในเหรียญ)
    cv2.circle(mask, (50, 50), 10, 255, 3)

    filled = fill_internal_holes(mask, max_hole_area=np.pi * 15**2)
    # รูเล็กต้องถูกเติม
    assert filled[50, 50] == 255
    # รูใหญ่ตรงกลางกรอบต้องไม่ถูกเติม
    assert filled[100, 100] == 0




