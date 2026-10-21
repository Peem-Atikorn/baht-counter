"""รัน eval/run_eval.py บนชุดข้อมูลสังเคราะห์ขนาดเล็ก ตรวจว่ารันได้คำสั่งเดียวและผลซ้ำได้"""
import json
import sys
from pathlib import Path

import cv2
import pytest

from modules.preprocess import mock_preprocess
from test_classification import make_image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import run_eval  # noqa: E402


@pytest.fixture(autouse=True)
def use_mock_preprocess(monkeypatch):
    """ภาพสังเคราะห์ในไฟล์นี้สูงแค่ ~230 px preprocess จริงของส่วนที่ 1 จะปฏิเสธว่าภาพเล็กเกินไป
    เทสต์นี้ตรวจตรรกะของ run_eval ไม่ใช่คุณภาพภาพ จึงใช้ mock_preprocess (ย่อภาพอย่างเดียว)"""
    monkeypatch.setattr(run_eval, "get_preprocess", lambda: mock_preprocess)

SETS = {
    "tune": [["THB_1", "THB_5", "THB_10"], ["THB_0_25", "THB_0_50", "THB_2"]],
    "test": [["THB_1", "THB_5", "THB_0_50"], ["THB_1", "THB_1"], ["THB_10", "THB_2", "THB_5", "THB_0_25"]],
}


def build_dataset(root: Path):
    (root / "raw").mkdir(parents=True)
    (root / "labels").mkdir()
    rows = ["image,split"]
    for split, images in SETS.items():
        for k, types in enumerate(images):
            name = f"{split}_{k}.png"
            pre, coins = make_image(types, seed=k)
            cv2.imwrite(str(root / "raw" / name), pre.image)
            labels = {"coins": [{"center_xy": list(c.center_xy), "radius_px": c.radius_px, "coin_type": t}
                                for c, t in zip(coins, types)]}
            (root / "labels" / f"{split}_{k}.json").write_text(json.dumps(labels), encoding="utf-8")
            rows.append(f"{name},{split}")
    (root / "splits.csv").write_text("\n".join(rows), encoding="utf-8")


def test_run_eval_gt_detector(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    build_dataset(data)
    args = ["--data", str(data), "--split", "test", "--detector", "gt", "--out", str(out)]
    run_eval.main(args)
    first = (out / "results_gt.json").read_text(encoding="utf-8")
    res = json.loads(first)["splits"]["test"]

    assert res["color+scale"]["det_recall"] == 1.0
    # ภาพเหรียญ 1 บาทล้วนต้องขอ anchor ยอดจึงระบุไม่ได้ 1 ใน 3 ภาพ
    assert res["color+scale"]["total_undecided_pct"] == 100 / 3
    # จำลองผู้ใช้กดเลือก 1 เหรียญแล้วถูกทุกเหรียญ
    assert res["color+scale+1"]["coin_accuracy"] == 1.0
    assert res["color+scale+1"]["total_exact_pct"] == 100.0
    assert res["baseline"]["coin_accuracy"] == 1.0   # ภาพสังเคราะห์ระยะเท่ากันหมด วิธีพื้นฐานจึงถูก

    run_eval.main(args)
    assert (out / "results_gt.json").read_text(encoding="utf-8") == first


def test_run_eval_unknown_label_not_used_as_anchor(tmp_path):
    """เหรียญที่ป้ายกำกับเป็น unknown และระบบยังไม่ตัดสินชนิด ต้องไม่ถูกเลือกเป็น anchor (เดิมล่มด้วย ValueError)"""
    data, out = tmp_path / "data", tmp_path / "out"
    build_dataset(data)
    pre, coins = make_image(["THB_1"])
    cv2.imwrite(str(data / "raw" / "test_unknown.png"), pre.image)
    labels = {"coins": [{"center_xy": list(coins[0].center_xy), "radius_px": coins[0].radius_px,
                         "coin_type": "unknown"}]}
    (data / "labels" / "test_unknown.json").write_text(json.dumps(labels), encoding="utf-8")
    with open(data / "splits.csv", "a", encoding="utf-8") as f:
        f.write("\ntest_unknown.png,test")

    run_eval.main(["--data", str(data), "--split", "test", "--detector", "gt", "--out", str(out)])
    res = json.loads((out / "results_gt.json").read_text(encoding="utf-8"))["splits"]["test"]
    assert res["color+scale+1"]["confusion"]["unknown"] == {"none": 1}
    assert res["color+scale"]["failed_pct"] == 0.0


def test_run_eval_template_method(tmp_path):
    """template จากชุด tune ทำให้ภาพ 5 บาทล้วนขนาดเดียวได้ยอดถูกโดยไม่ต้องถามผู้ใช้"""
    from test_classification_template import make_faces

    data, out = tmp_path / "data", tmp_path / "out"
    (data / "raw").mkdir(parents=True)
    (data / "labels").mkdir()
    sets = {
        "tune_0": ("tune", [("THB_1", 55, 0, None), ("THB_5", 66, 40, None)]),
        "test_0": ("test", [("THB_5", 50, 10, None), ("THB_5", 50, 130, None), ("THB_5", 50, 250, None)]),
    }
    rows = ["image,split"]
    for k, (name, (split, specs)) in enumerate(sets.items()):
        pre, coins = make_faces(specs, seed=k)
        cv2.imwrite(str(data / "raw" / f"{name}.png"), pre.image)
        labels = {"coins": [{"center_xy": list(c.center_xy), "radius_px": c.radius_px, "coin_type": s[0]}
                            for c, s in zip(coins, specs)]}
        (data / "labels" / f"{name}.json").write_text(json.dumps(labels), encoding="utf-8")
        rows.append(f"{name}.png,{split}")
    (data / "splits.csv").write_text("\n".join(rows), encoding="utf-8")

    run_eval.main(["--data", str(data), "--split", "test", "--detector", "gt", "--out", str(out)])
    res = json.loads((out / "results_gt.json").read_text(encoding="utf-8"))
    assert res["templates"] == {"THB_1": 1, "THB_5": 1}
    test = res["splits"]["test"]
    assert test["color+scale"]["total_undecided_pct"] == 100.0
    assert test["color+scale+template"]["total_exact_pct"] == 100.0
    assert test["color+scale+template"]["coin_accuracy"] == 1.0


def test_dump_colors(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    build_dataset(data)
    run_eval.main(["--data", str(data), "--split", "tune", "--out", str(out), "--dump-colors"])
    lines = (out / "colors_tune.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 + 6
