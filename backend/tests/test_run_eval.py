"""รัน eval/run_eval.py บนชุดข้อมูลสังเคราะห์ขนาดเล็ก ตรวจว่ารันได้คำสั่งเดียวและผลซ้ำได้"""
import json
import sys
from pathlib import Path

import cv2

from test_classification import make_image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
import run_eval  # noqa: E402

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


def test_dump_colors(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    build_dataset(data)
    run_eval.main(["--data", str(data), "--split", "tune", "--out", str(out), "--dump-colors"])
    lines = (out / "colors_tune.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 + 6
