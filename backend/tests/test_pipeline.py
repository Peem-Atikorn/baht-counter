import numpy as np
import pytest

from app import pipeline
from schemas import Coin


def test_pipeline_returns_original_coordinates():
    result, debug, timings = pipeline.run(np.zeros((3000, 4000, 3), np.uint8))
    assert result.image_size == (4000, 3000)
    assert max(c.center_xy[0] for c in result.coins) > 1600  # แปลงกลับจากภาพที่ย่อแล้ว
    assert "gray" in debug
    assert set(timings) == {"preprocess", "detection", "classification"}


def test_large_upload_coordinates_in_original_space():
    """main.decode_image ย่อภาพตอนถอดรหัส (ไม่ส่งภาพเต็มความละเอียดเข้า pipeline, รีวิว PR #39 ข้อ 3)
    พิกัดที่ได้ต้องเป็นพิกัดภาพต้นฉบับเป๊ะเหมือนเดิม ไม่ว่า pipeline จะได้รับภาพที่ถอดรหัสมาขนาดเท่าไร —
    ใช้ภาพต้นฉบับเดียวกับ test_pipeline_returns_original_coordinates (4000x3000) แต่ส่ง `image` ที่ย่อมา
    แล้วครึ่งหนึ่ง (2000x1500) พร้อม original_size เพื่อเทียบว่าพิกัดที่แปลงกลับตรงกันเป๊ะ"""
    full_result, _, _ = pipeline.run(np.zeros((3000, 4000, 3), np.uint8))

    decoded = np.zeros((1500, 2000, 3), np.uint8)  # main.decode_image ย่อ 4000x3000 มาเหลือ 2000x1500
    result, _, _ = pipeline.run(decoded, original_size=(4000, 3000))

    assert result.image_size == (4000, 3000)
    assert [c.center_xy for c in result.coins] == pytest.approx(
        [c.center_xy for c in full_result.coins],
    )


def test_add_coin_on_downscaled_image_keeps_original_coords():
    decoded = np.zeros((1500, 2000, 3), np.uint8)
    coin, is_fake = pipeline.locate_added_coin(decoded, (3500.0, 2500.0), [], original_size=(4000, 3000))
    assert is_fake is True
    assert coin.center_xy == pytest.approx((3500.0, 2500.0))


def test_reclassify_on_downscaled_image():
    """แก้ชนิดเหรียญบนภาพที่ถูกย่อตอนถอดรหัสมา (main.decode_image) — พิกัดเหรียญอื่น (ไม่ใช่ anchor) ต้อง
    ไม่เลื่อนจากที่เคยได้ตอน pipeline.run (รีวิว PR #39 ข้อ 3)"""
    decoded = np.zeros((1500, 2000, 3), np.uint8)
    original_size = (4000, 3000)
    result, _, _ = pipeline.run(decoded, original_size=original_size)
    before = {c.coin_id: c.center_xy for c in result.coins}

    reclassified = pipeline.reclassify(decoded, result.coins, anchor=(0, "THB_10"), original_size=original_size)

    assert reclassified.image_size == original_size
    for c in reclassified.coins:
        assert c.center_xy == pytest.approx(before[c.coin_id])


def test_pipeline_failure_is_reported(monkeypatch):
    def not_done(pre):
        raise NotImplementedError("detection ยังไม่เสร็จ")

    monkeypatch.setattr(pipeline.detection, "detect_coins", not_done)
    monkeypatch.setenv("COIN_USE_MOCK", "preprocess,classification")  # จำลองกรณีโมดูลจริงยังไม่เสร็จ
    result, _, timings = pipeline.run(np.zeros((100, 100, 3), np.uint8))
    assert result.status == "failed"
    assert "detection" in result.reason
    assert "preprocess" in timings


def test_mock_stages_empty_when_env_unset(monkeypatch):
    """ไม่ตั้ง COIN_USE_MOCK เลย (เหมือน docker compose/Render ที่ไม่ได้ override) = ของจริงทั้งหมด"""
    monkeypatch.delenv("COIN_USE_MOCK", raising=False)
    assert pipeline.mock_stages() == set()


def test_mock_stage_typo_is_rejected(monkeypatch):
    monkeypatch.setenv("COIN_USE_MOCK", "preprocess,detect")
    with pytest.raises(ValueError, match="detect"):
        pipeline.run(np.zeros((100, 100, 3), np.uint8))


def test_bad_anchor_is_raised(monkeypatch):
    def bad_anchor(pre, coins, anchor):
        raise ValueError("ไม่พบเหรียญ coin_id=99")

    monkeypatch.setattr(pipeline.classification, "mock_classify_coins", bad_anchor)
    with pytest.raises(ValueError):
        pipeline.run(np.zeros((100, 100, 3), np.uint8), anchor=(99, "THB_1"))


def test_reclassify_applies_anchor():
    image = np.zeros((600, 800, 3), np.uint8)
    result, _, _ = pipeline.run(image)
    reclassified = pipeline.reclassify(image, result.coins, anchor=(5, "THB_10"))
    assert reclassified.status == "ok"
    assert reclassified.scale_source == "user_anchor"
    edited = next(c for c in reclassified.coins if c.coin_id == 5)
    assert edited.coin_type == "THB_10"


def test_reclassify_does_not_reset_already_confirmed_coins(monkeypatch):
    """classify_coins จริง (ส่วนที่ 3) ใช้ source != estimated + coin_type ที่ส่งเข้าไปเป็น `fixed`
    เพื่อคงชนิดเดิมไว้ — pipeline ต้องไม่ล้างค่านี้ก่อนส่งเข้าไป ไม่งั้นชนิดที่ผู้ใช้เลือกไว้ก่อนจะหาย
    (รีวิว PR #19 ข้อ 3) เทสต์นี้ตรวจสิ่งที่ pipeline ส่งเข้า classify_coins โดยไม่พึ่งพฤติกรรมของ mock/ของจริง
    """
    captured: dict[str, list[Coin]] = {}

    def fake_classify(pre, coins, anchor):
        captured["coins"] = coins
        return pipeline.CountResult(
            image_size=pre.original_size, coins=coins, total_baht=None,
            scale_mm_per_px=None, scale_source=None, status="ok", reason=None,
        )

    monkeypatch.setattr(pipeline.classification, "mock_classify_coins", fake_classify)

    confirmed = Coin(
        coin_id=0, center_xy=(10.0, 10.0), radius_px=5.0,
        coin_type="THB_10", value_baht=10.0, source="user_edited", status="ok",
    )
    guessed = Coin(coin_id=1, center_xy=(20.0, 20.0), radius_px=5.0, status="needs_confirmation")
    image = np.zeros((600, 800, 3), np.uint8)

    pipeline.reclassify(image, [confirmed, guessed], anchor=None)

    passed = {c.coin_id: c for c in captured["coins"]}
    assert passed[0].coin_type == "THB_10"  # ผู้ใช้ยืนยันไว้แล้ว ไม่ถูกล้าง
    assert passed[0].status == "ok"
    assert passed[1].coin_type is None  # เหรียญที่ระบบเดาเองยังถูกล้างตามปกติ
    assert passed[1].status == "ok"  # สถานะ needs_confirmation ค้างเดิมถูกรีเซ็ต


def test_locate_added_coin_uses_detect_coin_at_when_available(monkeypatch):
    located = Coin(coin_id=0, center_xy=(10.0, 10.0), radius_px=99.0)
    monkeypatch.setattr(pipeline.detection, "detect_coin_at", lambda pre, xy: located, raising=False)
    image = np.zeros((600, 800, 3), np.uint8)
    result = pipeline.locate_added_coin(image, (100.0, 50.0), [])
    assert result == (located, False)


def test_locate_added_coin_falls_back_to_median_radius_of_existing_coins():
    image = np.zeros((600, 800, 3), np.uint8)
    existing = [
        Coin(coin_id=0, center_xy=(0, 0), radius_px=10.0),
        Coin(coin_id=1, center_xy=(0, 0), radius_px=20.0),
        Coin(coin_id=2, center_xy=(0, 0), radius_px=30.0),
    ]
    coin, is_fake = pipeline.locate_added_coin(image, (100.0, 50.0), existing)
    assert is_fake is True
    assert coin.center_xy == (100.0, 50.0)
    assert coin.radius_px == 20.0  # มัธยฐาน, resize_factor = 1 เพราะภาพเล็กกว่า TARGET_LONG_SIDE


def test_locate_added_coin_falls_back_to_image_fraction_when_no_other_coins():
    image = np.zeros((600, 800, 3), np.uint8)
    coin, is_fake = pipeline.locate_added_coin(image, (100.0, 50.0), [])
    assert is_fake is True
    assert coin.radius_px == pytest.approx(pipeline.FALLBACK_RADIUS_FRACTION * 600)
