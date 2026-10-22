"""ทดสอบ eval/detection_baselines.py บนภาพตัวอย่าง ตรวจว่ารันผ่านและได้ผลครบทุกวิธี"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import detection_baselines  # noqa: E402


def test_detection_baselines_on_samples(tmp_path):
    data = ROOT / "data"
    out = tmp_path / "results"
    args = ["--data", str(data), "--split", "samples", "--out", str(out)]
    detection_baselines.main(args)

    md_file = out / "detection_baselines_samples.md"
    json_file = out / "detection_baselines_samples.json"

    assert md_file.exists()
    assert json_file.exists()

    res = json.loads(json_file.read_text(encoding="utf-8"))
    assert res["images_count"] >= 1
    assert res["gt_coins_count"] >= 1

    methods = res["methods"]
    for m in [
        "Proposed (Multi-cue + Watershed)",
        "Baseline A: No Watershed",
        "Baseline B: K-Means",
        "Baseline C: Hough Circles",
    ]:
        assert m in methods
        assert 0.0 <= methods[m]["precision"] <= 1.0
        assert 0.0 <= methods[m]["recall"] <= 1.0
        assert 0.0 <= methods[m]["f1_score"] <= 1.0
        assert methods[m]["mean_radius_error_pct"] >= 0.0


def test_detection_baselines_missing_images_exit():
    data = ROOT / "data"
    with pytest.raises(SystemExit) as exc:
        detection_baselines.evaluate_baselines(data, ["missing_sample_image.jpg"])
    assert "ไม่พบภาพ" in str(exc.value)
