"""เครื่องมือชุดข้อมูลของส่วนที่ 1: data/dataset.py และ data/preprocess_experiment.py"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from test_classification import make_image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))
import dataset  # noqa: E402
import preprocess_experiment  # noqa: E402

TYPES = ["THB_1", "THB_5", "THB_10"]


def add_image(data: Path, name: str, coins=None, size=(400, 300), label=True):
    """ภาพพื้นเรียบ + ป้ายกำกับ (เครื่องมือ check/split ไม่ได้ประมวลผลภาพ)"""
    (data / "raw").mkdir(parents=True, exist_ok=True)
    (data / "labels").mkdir(exist_ok=True)
    cv2.imwrite(str(data / "raw" / name), np.full((size[1], size[0], 3), 120, np.uint8))
    if label:
        coins = coins if coins is not None else [
            {"center_xy": [50 + 100 * k, 150], "radius_px": 40, "coin_type": t} for k, t in enumerate(TYPES)]
        (data / "labels" / f"{Path(name).stem}.json").write_text(json.dumps({"coins": coins}), encoding="utf-8")


def test_protocol_group():
    assert dataset.protocol_group("p1_white_room_top_001.jpg") == ("white", "room", "top")
    assert dataset.protocol_group("IMG_1234.jpg") is None


def test_check_counts_and_reports_problems(tmp_path):
    add_image(tmp_path, "p1_white_room_top_001.png")
    add_image(tmp_path, "p1_wood_window_tilt15_002.png")
    add_image(tmp_path, "IMG_9.png")                       # ชื่อผิดรูปแบบ
    add_image(tmp_path, "p1_white_room_top_003.png", label=False)
    add_image(tmp_path, "p1_cloth_flash_top_004.png", coins=[
        {"center_xy": [900, 10], "radius_px": 40, "coin_type": "THB_1"},   # นอกภาพ
        {"center_xy": [10, 10], "radius_px": 40, "coin_type": "THB_3"},    # ชนิดไม่มีจริง
    ])
    (tmp_path / "labels" / "ghost.json").write_text('{"coins": []}', encoding="utf-8")

    rep = dataset.check(tmp_path)
    errors, warnings, text = "\n".join(rep.errors), "\n".join(rep.warnings), "\n".join(rep.lines)
    assert "ghost.json" in errors
    assert "อยู่นอกภาพ" in errors and "THB_3" in errors
    assert "p1_white_room_top_003.png: ยังไม่มีป้ายกำกับ" in warnings
    assert "IMG_9.png: ชื่อไม่ตรงรูปแบบ" in warnings
    assert "ยังไม่อยู่ใน splits.csv" in warnings
    assert "| THB_1 | 3 ⚠ |" in text                     # 3 ภาพที่ป้ายถูก × 1 เหรียญ ต่ำกว่าเป้า 80
    assert "- พื้นหลัง: {'cloth': 1, 'white': 2, 'wood': 1}" in rep.lines   # 3 แบบครบแล้ว ไม่มี ⚠
    assert "- แสง: {'flash': 1, 'room': 2, 'window': 1}" in rep.lines
    assert dataset.main(["--data", str(tmp_path), "check"]) == 1


def test_check_uses_exif_orientation(tmp_path):
    """ภาพแนวตั้งจากมือถือ: ไฟล์เก็บเป็น 400x300 + EXIF หมุน 90° ป้ายกำกับใช้พิกัดหลังหมุน (300x400)"""
    (tmp_path / "raw").mkdir(parents=True)
    (tmp_path / "labels").mkdir()
    exif = Image.Exif()
    exif[dataset.EXIF_ORIENTATION] = 6
    Image.new("RGB", (400, 300)).save(tmp_path / "raw" / "p1_white_room_top_001.jpg", exif=exif)
    coins = [{"center_xy": [150, 350], "radius_px": 30, "coin_type": t} for t in TYPES]
    (tmp_path / "labels" / "p1_white_room_top_001.json").write_text(
        json.dumps({"image_size": [300, 400], "coins": coins}), encoding="utf-8")
    assert dataset.check(tmp_path).errors == []


def test_split_is_stratified_and_never_moves_existing(tmp_path):
    for k in range(10):
        add_image(tmp_path, f"p1_white_room_top_{k:03d}.png")
        add_image(tmp_path, f"p2_wood_window_tilt15_{k:03d}.png")
    add_image(tmp_path, "web_001.png")
    add_image(tmp_path, "p1_white_room_top_099.png", label=False)   # ไม่มีป้าย ไม่ถูกจัด

    assert dataset.main(["--data", str(tmp_path), "split", "--test-frac", "0.3"]) == 0
    first = dataset.load_splits(tmp_path)
    assert first["web_001.png"] == "web"
    assert "p1_white_room_top_099.png" not in first
    for prefix in ("p1_white", "p2_wood"):
        assert sum(s == "test" for n, s in first.items() if n.startswith(prefix)) == 3

    # รันซ้ำได้ผลเดิม และภาพใหม่ไม่ทำให้ภาพเดิมย้าย split
    for k in range(10, 20):
        add_image(tmp_path, f"p1_white_room_top_{k:03d}.png")
    dataset.main(["--data", str(tmp_path), "split", "--test-frac", "0.3"])
    second = dataset.load_splits(tmp_path)
    assert {n: second[n] for n in first} == first
    assert sum(s == "test" for n, s in second.items() if n.startswith("p1_white")) == 6
    assert dataset.check(tmp_path).errors == []


def test_split_dry_run_does_not_write(tmp_path):
    add_image(tmp_path, "p1_white_room_top_001.png")
    dataset.main(["--data", str(tmp_path), "split", "--dry-run"])
    assert not (tmp_path / "splits.csv").exists()


def test_split_after_test_lock_sends_new_images_to_tune(tmp_path):
    """หลังล็อกชุด test: --test-frac 0 ภาพใหม่ไป tune ทั้งหมด ชุด test เดิมไม่โตขึ้น"""
    for k in range(10):
        add_image(tmp_path, f"p1_white_room_top_{k:03d}.png")
    dataset.main(["--data", str(tmp_path), "split"])
    locked = {n for n, s in dataset.load_splits(tmp_path).items() if s == "test"}

    for k in range(10, 20):
        add_image(tmp_path, f"p1_white_room_top_{k:03d}.png")
    dataset.main(["--data", str(tmp_path), "split", "--test-frac", "0"])
    after = dataset.load_splits(tmp_path)
    assert {n for n, s in after.items() if s == "test"} == locked
    assert all(after[f"p1_white_room_top_{k:03d}.png"] == "tune" for k in range(10, 20))


def test_preprocess_experiment_without_splits_exits_cleanly(tmp_path, capsys):
    assert preprocess_experiment.main(["--data", str(tmp_path), "--out", str(tmp_path / "out")]) == 1
    assert "dataset.py split" in capsys.readouterr().err


def test_preprocess_experiment_runs_end_to_end(tmp_path):
    """ภาพสังเคราะห์ใหญ่พอผ่านการตรวจคุณภาพ ทุกวิธีต้องหาเหรียญเจอและจัดกลุ่มสีถูก"""
    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)
    (data / "labels").mkdir()
    rows = ["image,split"]
    for k, types in enumerate([["THB_1", "THB_5", "THB_10"], ["THB_0_50", "THB_2", "THB_1"]]):
        pre, coins = make_image(types, px_per_mm=14, glare=False, seed=k)
        name = f"p1_gray_room_top_{k:03d}.png"
        cv2.imwrite(str(data / "raw" / name), pre.image)
        labels = [{"center_xy": list(c.center_xy), "radius_px": c.radius_px, "coin_type": t}
                  for c, t in zip(coins, types)]
        (data / "labels" / f"{Path(name).stem}.json").write_text(json.dumps({"coins": labels}), encoding="utf-8")
        rows.append(f"{name},tune")
    (data / "splits.csv").write_text("\n".join(rows), encoding="utf-8")

    out = tmp_path / "out"
    preprocess_experiment.main(["--data", str(data), "--out", str(out)])
    res = json.loads((out / "preprocess_experiment.json").read_text(encoding="utf-8"))["tune"]
    assert set(res) == set(preprocess_experiment.VARIANTS)
    for name, s in res.items():
        assert s["rejected"] == 0, (name, s["reject_reasons"])
        assert s["det_recall"] == pytest.approx(1.0), name
        assert s["color_group_acc"] == pytest.approx(1.0), name
    assert "| clahe+wb |" in (out / "preprocess_experiment.md").read_text(encoding="utf-8")


def test_import_web_export_restores_protocol_names(tmp_path):
    """zip รูปแบบเดียวกับ GET /api/labels/export: ไฟล์ชื่อ analysis_id, ชื่อเดิมอยู่ใน source_filename"""
    import zipfile

    _, png = cv2.imencode(".png", np.full((300, 400, 3), 120, np.uint8))
    coins = [{"center_xy": [50 + 100 * k, 150], "radius_px": 40, "coin_type": t} for k, t in enumerate(TYPES)]
    zip_path = tmp_path / "labels.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for aid, source in [("aaa", "p1_white_room_top_001.png"), ("bbb", "capture.jpg"), ("ccc", "web_001.png")]:
            label = {"image": f"{aid}.png", "source_filename": source, "image_size": [400, 300],
                     "coins": coins, "notes": ""}
            zf.writestr(f"labels/{aid}.json", json.dumps(label))
            zf.writestr(f"raw/{aid}.png", png.tobytes())

    data = tmp_path / "data"
    imported, skipped = dataset.import_export(data, zip_path)
    assert imported == ["p1_white_room_top_001.png", "bbb.png", "web_001.png"]
    assert skipped == []
    label = json.loads((data / "labels" / "p1_white_room_top_001.json").read_text(encoding="utf-8"))
    assert label["image"] == "p1_white_room_top_001.png"
    assert dataset.check(data).errors == []

    # นำเข้าซ้ำไม่เขียนทับ
    imported, skipped = dataset.import_export(data, zip_path)
    assert imported == [] and len(skipped) == 3


def test_import_does_not_write_outside_raw(tmp_path):
    """ชื่อภาพใน zip ที่มี ../ ต้องไม่เขียนไฟล์ออกนอก data/raw"""
    import zipfile

    zip_path = tmp_path / "labels.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("labels/x.json", json.dumps({"image": "../../evil.png", "source_filename": "capture.jpg",
                                                 "coins": []}))
        zf.writestr("raw/evil.png", b"png")
    data = tmp_path / "data"
    imported, _ = dataset.import_export(data, zip_path)
    assert imported == ["evil.png"]
    assert (data / "raw" / "evil.png").exists()
    assert not (tmp_path / "evil.png").exists()
