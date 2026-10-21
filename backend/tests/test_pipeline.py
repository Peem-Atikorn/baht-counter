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


def test_pipeline_failure_is_reported(monkeypatch):
    monkeypatch.setenv("COIN_USE_MOCK", "preprocess,classification")  # detection จริงยังไม่เสร็จ
    result, _, timings = pipeline.run(np.zeros((100, 100, 3), np.uint8))
    assert result.status == "failed"
    assert "detection" in result.reason
    assert "preprocess" in timings


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


def test_locate_added_coin_defaults_when_no_detect_coin_at():
    image = np.zeros((600, 800, 3), np.uint8)
    coin = pipeline.locate_added_coin(image, (100.0, 50.0))
    assert isinstance(coin, Coin)
    assert coin.center_xy == (100.0, 50.0)
    assert coin.radius_px == pipeline.DEFAULT_ADD_RADIUS_PX  # resize_factor = 1 เพราะภาพเล็กกว่า TARGET_LONG_SIDE
