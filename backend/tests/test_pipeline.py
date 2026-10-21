import numpy as np

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
    assert result.reason
