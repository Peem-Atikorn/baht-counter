import numpy as np
import pytest

from app import pipeline


def test_pipeline_returns_original_coordinates():
    result, debug = pipeline.run(np.zeros((3000, 4000, 3), np.uint8))
    assert result.image_size == (4000, 3000)
    assert max(c.center_xy[0] for c in result.coins) > 1600  # แปลงกลับจากภาพที่ย่อแล้ว
    assert "gray" in debug


def test_pipeline_failure_is_reported(monkeypatch):
    monkeypatch.setenv("COIN_USE_MOCK", "preprocess,classification")  # detection จริงยังไม่เสร็จ
    result, _ = pipeline.run(np.zeros((100, 100, 3), np.uint8))
    assert result.status == "failed"
    assert "detection" in result.reason


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
