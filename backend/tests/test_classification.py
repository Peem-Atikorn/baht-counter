"""เทสต์ส่วนที่ 3 — classify_coins ใช้ภาพสังเคราะห์ (วาดเหรียญสีเรียบบนพื้นเทา) ยังไม่ต้องรอภาพจริง"""
import cv2
import numpy as np
import pytest

from modules.classification import (
    COIN_SPECS, classify_coins, classify_coins_baseline, draw_color_groups,
    fit_baseline_scale, mock_classify_coins, radius_ranges_px, total_baht,
)
from modules.classification.color import color_groups
from modules.classification.scale import fit_scale
from modules.detection import mock_detect_coins
from modules.preprocess import mock_preprocess
from schemas import Coin, CountResult, PreprocessResult

# สี BGR ที่ให้ HSV ตรงกลุ่ม
COLORS = {
    "copper": (60, 100, 190),
    "silver": (175, 178, 182),
    "gold": (50, 175, 215),
}
PX_PER_MM = 5.0


def make_image(coin_types, px_per_mm=PX_PER_MM, glare=True, seed=0):
    """วาดเหรียญเรียงแถว คืน (PreprocessResult, list[Coin]) ที่จุดศูนย์กลาง/รัศมีถูกต้อง"""
    rng = np.random.default_rng(seed)
    w = int(sum(COIN_SPECS[t].diameter_mm * px_per_mm + 40 for t in coin_types)) + 40
    h = int(30 * px_per_mm) + 80
    img = np.full((h, w, 3), 110, np.uint8)
    coins, x = [], 40.0
    for i, t in enumerate(coin_types):
        r = COIN_SPECS[t].diameter_mm * px_per_mm / 2
        cx, cy = x + r, h / 2
        group = COIN_SPECS[t].color_group
        if group == "bimetal":
            cv2.circle(img, (round(cx), round(cy)), round(r), COLORS["silver"], -1)
            cv2.circle(img, (round(cx), round(cy)), round(r * 0.62), COLORS["gold"], -1)
        else:
            cv2.circle(img, (round(cx), round(cy)), round(r), COLORS[group], -1)
        if glare:
            cv2.circle(img, (round(cx - r * 0.3), round(cy - r * 0.3)), max(2, round(r * 0.15)), (255, 255, 255), -1)
        coins.append(Coin(coin_id=i, center_xy=(cx, cy), radius_px=r))
        x += 2 * r + 40
    noise = rng.normal(0, 4, img.shape)
    img = np.clip(img + noise, 0, 255).astype(np.uint8)
    pre = PreprocessResult(image=img, gray=cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
                           resize_factor=1.0, original_size=(w, h), status="ok")
    return pre, coins


@pytest.mark.parametrize("t", list(COIN_SPECS))
def test_color_group_each_type(t):
    pre, coins = make_image([t])
    assert color_groups(pre.image, coins)[0].group == COIN_SPECS[t].color_group


def test_mixed_coins_scale_inferred():
    types = ["THB_0_25", "THB_0_50", "THB_1", "THB_2", "THB_5", "THB_10", "THB_1"]
    pre, coins = make_image(types)
    res = classify_coins(pre, coins)
    assert [c.coin_type for c in res.coins] == types
    assert res.status == "ok"
    assert res.scale_source == "inferred"
    assert res.scale_mm_per_px == pytest.approx(1 / PX_PER_MM, rel=0.02)
    assert res.total_baht == pytest.approx(0.25 + 0.5 + 1 + 2 + 5 + 10 + 1)


def test_scale_does_not_need_real_size():
    """ย่อ/ขยายภาพทั้งภาพ ชนิดต้องเหมือนเดิม (ไม่ต้องรู้ระยะถ่าย)"""
    types = ["THB_1", "THB_5", "THB_0_50", "THB_10"]
    for px_per_mm in (3.0, 8.0):
        res = classify_coins(*make_image(types, px_per_mm=px_per_mm))
        assert [c.coin_type for c in res.coins] == types


def test_single_silver_size_needs_anchor():
    pre, coins = make_image(["THB_1", "THB_1", "THB_1"])
    res = classify_coins(pre, coins)
    assert res.status == "needs_confirmation"
    assert res.total_baht is None            # ห้ามตอบ 0
    assert res.scale_mm_per_px is None
    assert all(c.coin_type is None and c.value_baht is None for c in res.coins)
    assert "เลือกชนิด" in res.reason


def test_anchor_resolves_scale():
    pre, coins = make_image(["THB_5", "THB_5", "THB_5"])
    res = classify_coins(pre, coins, anchor=(1, "THB_5"))
    assert res.status == "ok"
    assert res.scale_source == "user_anchor"
    assert [c.coin_type for c in res.coins] == ["THB_5"] * 3
    assert res.coins[1].source == "user_edited"
    assert res.total_baht == 15.0


def test_gold_only_is_not_ambiguous():
    """กลุ่มสีที่มีชนิดเดียว ไม่ต้องรู้สเกลก็บอกชนิดได้"""
    res = classify_coins(*make_image(["THB_2", "THB_10"]))
    assert res.status == "ok"
    assert res.total_baht == 12.0


def test_user_edited_coin_kept_and_used_as_constraint():
    pre, coins = make_image(["THB_1", "THB_1"])
    coins[0] = coins[0].model_copy(update=dict(coin_type="THB_1", source="user_edited"))
    res = classify_coins(pre, coins)
    assert [c.coin_type for c in res.coins] == ["THB_1", "THB_1"]
    assert res.coins[0].source == "user_edited"
    assert res.status == "ok"


def test_unknown_size_coin_makes_total_null():
    """เหรียญทองขนาดไม่ตรงกับ 2 บาท (เช่นเหรียญต่างประเทศ) -> unknown ไม่ใช่เดา และยอดรวมเป็น null ไม่นับเป็น 0"""
    pre, coins = make_image(["THB_1", "THB_5", "THB_2"])
    # ใหญ่กว่า 2 บาท 45% (MAX_REL_ERR ปรับด้วยชุด tune เป็น 0.13 เพราะมุมกล้องทำให้ขนาดคลาดได้มาก)
    big = coins[2].model_copy(update=dict(radius_px=coins[2].radius_px * 1.45))
    res = classify_coins(pre, coins[:2] + [big])
    assert res.coins[2].coin_type == "unknown"
    assert res.coins[2].value_baht is None
    assert res.status == "needs_confirmation"
    assert res.total_baht is None
    # ผู้ใช้ลบเหรียญนั้นแล้ว ยอดรวมกลับมาเป็นตัวเลข
    assert classify_coins(pre, coins[:2]).total_baht == 6.0


def test_unknown_change_does_not_force_anchor():
    """10 บาท 2 เหรียญขนาดต่างกัน 8%: คำตอบต่างกันแค่ว่าเหรียญไหนเป็น unknown ไม่ควรขอ anchor"""
    pre, coins = make_image(["THB_10", "THB_10"])
    coins = [coins[0].model_copy(update=dict(radius_px=50.0)),
             coins[1].model_copy(update=dict(radius_px=54.0))]
    res = classify_coins(pre, coins)
    assert res.scale_mm_per_px is not None
    assert res.scale_source == "inferred"
    assert "1 เหรียญ เพื่อให้ระบบคำนวณที่เหลือ" not in (res.reason or "")


def test_pale_gold_ring_is_not_bimetal():
    """ขอบ 2 บาทซีดกว่าใจกลาง (ยังเป็นสีทอง) ต้องเป็น gold ไม่ใช่ bimetal"""
    pre, coins = make_image(["THB_2"], glare=False)
    c = coins[0]
    cv2.circle(pre.image, (round(c.center_xy[0]), round(c.center_xy[1])), round(c.radius_px), (90, 180, 215), -1)
    cv2.circle(pre.image, (round(c.center_xy[0]), round(c.center_xy[1])), round(c.radius_px * 0.6), COLORS["gold"], -1)
    f = color_groups(pre.image, coins)[0]
    assert f.inner_label == f.ring_label == "gold"
    assert f.inner_hsv[1] - f.ring_hsv[1] >= 35    # เดิมเงื่อนไขนี้ทำให้กลายเป็นสองสี
    assert f.group == "gold"


def test_old_silver_2_baht_flagged():
    pre, coins = make_image(["THB_1", "THB_5", "THB_10", "THB_1"])
    mid = coins[3].model_copy(update=dict(radius_px=21.75 * PX_PER_MM / 2))
    res = classify_coins(pre, coins[:3] + [mid])
    assert res.coins[3].coin_type is None
    assert res.coins[3].status == "needs_confirmation"
    assert res.total_baht is None


def test_ellipse_major_axis_used():
    pre, coins = make_image(["THB_1", "THB_5"])
    tilted = [c.model_copy(update=dict(ellipse=(2 * c.radius_px, 2 * c.radius_px * 0.85, 30.0),
                                       radius_px=c.radius_px * 0.92)) for c in coins]
    res = classify_coins(pre, tilted)
    assert [c.coin_type for c in res.coins] == ["THB_1", "THB_5"]


def test_no_coins_and_failed_preprocess():
    pre, _ = make_image(["THB_1"])
    assert classify_coins(pre, []).status == "failed"
    bad = PreprocessResult(image=None, gray=None, resize_factor=1.0, original_size=(800, 600),
                           status="failed", reason="ภาพเบลอ กรุณาถือกล้องให้นิ่ง")
    res = classify_coins(bad, [])
    assert res.status == "failed" and res.reason == "ภาพเบลอ กรุณาถือกล้องให้นิ่ง"
    assert res.total_baht is None


def test_invalid_anchor_raises():
    pre, coins = make_image(["THB_1"])
    with pytest.raises(ValueError):
        classify_coins(pre, coins, anchor=(99, "THB_1"))
    with pytest.raises(ValueError):
        classify_coins(pre, coins, anchor=(0, "THB_3"))


def test_fit_scale_robust_to_outlier():
    """วัตถุแปลกปลอม 1 ชิ้นไม่ควรดึงสเกลของทั้งภาพ"""
    d = [100.0, 120.0, 100.0, 120.0, 333.0]
    cands = [["THB_1", "THB_5"]] * 4 + [["THB_1", "THB_5"]]
    fit = fit_scale(d, cands)
    assert fit.best.scale == pytest.approx(0.2)
    assert fit.best.types == ["THB_1", "THB_5", "THB_1", "THB_5", "unknown"]


def test_baseline():
    types = ["THB_0_25", "THB_1", "THB_5", "THB_10"]
    pre, coins = make_image(types)
    s = fit_baseline_scale([2 * c.radius_px for c in coins], types)
    assert s == pytest.approx(1 / PX_PER_MM)
    res = classify_coins_baseline(pre, coins, s)
    assert [c.coin_type for c in res.coins] == types
    # ถ่ายใกล้ขึ้น วิธีพื้นฐานผิด แต่วิธีหาสเกลยังถูก
    pre2, coins2 = make_image(types, px_per_mm=PX_PER_MM * 1.25)
    assert [c.coin_type for c in classify_coins_baseline(pre2, coins2, s).coins] != types
    assert [c.coin_type for c in classify_coins(pre2, coins2).coins] == types
    ranges = radius_ranges_px(s)
    assert ranges["THB_1"][0] < 20 * PX_PER_MM / 2 < ranges["THB_1"][1]


def test_debug_image():
    pre, coins = make_image(["THB_1", "THB_10"])
    out = draw_color_groups(pre.image, classify_coins(pre, coins))
    assert out.shape == pre.image.shape


# ---------- mock ----------

def test_mock_chain_matches_schema():
    pre = mock_preprocess(np.zeros((3000, 4000, 3), np.uint8))
    assert max(pre.gray.shape) == 1600
    coins = mock_detect_coins(pre)
    result = mock_classify_coins(pre, coins)
    CountResult.model_validate(result.model_dump())
    assert result.status == "needs_confirmation"
    assert result.total_baht is None  # มีเหรียญที่ระบุไม่ได้ ห้ามรวมเป็นตัวเลข


def test_anchor_resolves_confirmation():
    pre = mock_preprocess(np.zeros((600, 800, 3), np.uint8))
    coins = mock_detect_coins(pre)
    result = mock_classify_coins(pre, coins, anchor=(5, "THB_10"))
    assert result.status == "ok"
    assert result.scale_source == "user_anchor"
    assert result.total_baht == 18.75


def test_total_baht_none_when_unknown():
    coins = [
        Coin(coin_id=0, center_xy=(0, 0), radius_px=1, value_baht=5.0),
        Coin(coin_id=1, center_xy=(0, 0), radius_px=1, value_baht=None),
    ]
    assert total_baht(coins) is None
    assert total_baht(coins[:1]) == 5.0
