import cv2
import numpy as np
import pytest

from app import pipeline
from modules import preprocess as pp

H, W = 1200, 1600


def coin_photo(bg: int = 225, seed: int = 0) -> np.ndarray:
    """ภาพสังเคราะห์: เหรียญ 12 เหรียญ (เงิน/ทอง/ทองแดง) บนพื้นสีเรียบ พร้อมจุดรบกวนเล็กน้อย"""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), bg, np.uint8)
    for i in range(12):
        c = (int(rng.integers(150, W - 150)), int(rng.integers(150, H - 150)))
        r = int(rng.integers(55, 85))
        color = [(190, 190, 195), (60, 170, 215), (60, 110, 190)][i % 3]
        cv2.circle(img, c, r, color, -1, cv2.LINE_AA)
        cv2.circle(img, c, int(r * 0.6), tuple(max(0, v - 40) for v in color), 3, cv2.LINE_AA)
    return (img + rng.normal(0, 4, img.shape)).clip(0, 255).astype(np.uint8)


def motion_blur(img: np.ndarray, k: int) -> np.ndarray:
    kernel = np.zeros((k, k), np.float32)
    kernel[k // 2, :] = 1 / k
    return cv2.filter2D(img, -1, kernel)


@pytest.mark.parametrize("bg", [225, 40], ids=["white-paper", "dark-cloth"])
def test_sharp_photo_passes(bg):
    """พื้นผ้าสีเข้มมีค่าเฉลี่ยต่ำ แต่ไม่ใช่ภาพมืด ต้องผ่าน"""
    result = pp.preprocess(coin_photo(bg))
    assert result.status == "ok", result.reason
    assert result.reason is None


@pytest.mark.parametrize(
    "make_bad, message",
    [
        (lambda img: cv2.GaussianBlur(img, (0, 0), 4), pp.MSG_BLURRY),
        (lambda img: motion_blur(img, 15), pp.MSG_BLURRY),
        (lambda img: (img * 0.25).astype(np.uint8), pp.MSG_TOO_DARK),
        (lambda img: np.clip(img.astype(int) + 90, 0, 255).astype(np.uint8), pp.MSG_TOO_BRIGHT),
        (lambda img: np.full_like(img, 230), pp.MSG_FLAT),
        (lambda img: cv2.resize(img, (400, 300)), pp.MSG_TOO_SMALL.format(n=pp.MIN_SHORT_SIDE)),
    ],
    ids=["gaussian-blur", "motion-blur", "too-dark", "too-bright", "flat", "too-small"],
)
def test_bad_photo_is_rejected_with_thai_reason(make_bad, message):
    result = pp.preprocess(make_bad(coin_photo()))
    assert result.status == "failed"
    assert result.reason == message


def test_resizes_long_side_and_keeps_colors():
    image = cv2.resize(coin_photo(), (3200, 2400))
    result = pp.preprocess(image)
    assert result.image.shape[:2] == (1200, 1600)
    assert result.resize_factor == pytest.approx(0.5)
    assert result.original_size == (3200, 2400)
    # ส่วนที่ 3 วัดสีจาก result.image จึงต้องเป็นภาพย่อธรรมดา ไม่ผ่าน CLAHE
    plain = cv2.resize(image, (1600, 1200), interpolation=cv2.INTER_AREA)
    assert np.array_equal(result.image, plain)


def test_does_not_upscale_small_images():
    image = cv2.resize(coin_photo(), (800, 600))
    result = pp.preprocess(image)
    assert result.resize_factor == 1.0
    assert result.image.shape[:2] == (600, 800)


def test_gray_is_enhanced_and_debug_images_are_returned():
    image = coin_photo()
    result = pp.preprocess(image)
    plain_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    assert result.gray.shape == plain_gray.shape
    assert not np.array_equal(result.gray, plain_gray)  # ผ่าน CLAHE + median แล้ว
    assert set(result.debug_images) == {"gray", "clahe", "enhanced"}
    assert np.array_equal(result.debug_images["enhanced"], result.gray)


def test_failed_photo_still_returns_images_for_about_page():
    result = pp.preprocess(cv2.GaussianBlur(coin_photo(), (0, 0), 4))
    assert result.status == "failed"
    assert result.image is not None and result.gray is not None
    assert "gray" in result.debug_images


def test_pipeline_uses_real_preprocess_reason(monkeypatch):
    monkeypatch.setenv("COIN_USE_MOCK", "detection,classification")
    ok, debug, _ = pipeline.run(coin_photo())
    assert ok.status != "failed"
    assert {"gray", "clahe", "enhanced"} <= set(debug)

    blurry, _, _ = pipeline.run(motion_blur(coin_photo(), 15))
    assert blurry.status == "failed"
    assert blurry.reason == pp.MSG_BLURRY
