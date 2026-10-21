"""เครื่องมือติดป้าย data/label_tool.py (ส่วนที่ 1) — ทดสอบเฉพาะส่วนที่ไม่ใช้หน้าต่าง GUI"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))
import dataset  # noqa: E402
import label_tool  # noqa: E402


def make_raw(data: Path, name: str, size=(400, 300), orientation=None):
    (data / "raw").mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (120, 120, 120))
    exif = Image.Exif()
    if orientation:
        exif[dataset.EXIF_ORIENTATION] = orientation
    img.save(data / "raw" / name, exif=exif.tobytes())


def test_saved_label_passes_dataset_check(tmp_path):
    data = tmp_path / "data"
    name = "p1_white_room_top_001.jpg"
    make_raw(data, name)
    coins = [{"center_xy": [100.04, 150.0], "radius_px": 40.26, "coin_type": t}
             for t in ("THB_1", "THB_5", "THB_10")]
    for k, c in enumerate(coins):
        c["center_xy"][0] += 100 * k
    label_tool.save_label(data, name, label_tool.load_image(data / "raw" / name).size, coins)

    doc = json.loads((data / "labels" / "p1_white_room_top_001.json").read_text(encoding="utf-8"))
    assert doc["image"] == name and doc["image_size"] == [400, 300]
    assert doc["coins"][0] == {"center_xy": [100.0, 150.0], "radius_px": 40.3, "coin_type": "THB_1"}
    assert dataset.check(data).errors == []

    coins_back, notes = label_tool.load_label(data, name)
    assert [c["coin_type"] for c in coins_back] == ["THB_1", "THB_5", "THB_10"] and notes == ""


def test_load_image_follows_exif_like_dataset(tmp_path):
    """ภาพที่ EXIF สั่งหมุน 90° ต้องได้ขนาดเดียวกับที่ dataset.check ใช้ตรวจ image_size"""
    data = tmp_path / "data"
    make_raw(data, "p1_white_room_top_002.jpg", size=(400, 300), orientation=6)
    path = data / "raw" / "p1_white_room_top_002.jpg"
    assert label_tool.load_image(path).size == dataset.oriented_size(path) == (300, 400)


def test_coin_at_prefers_closest_center_when_overlapping():
    coins = [{"center_xy": [100, 100], "radius_px": 60, "coin_type": "THB_10"},
             {"center_xy": [150, 100], "radius_px": 40, "coin_type": "THB_1"}]
    assert label_tool.coin_at(coins, 140, 100) == 1
    assert label_tool.coin_at(coins, 80, 100) == 0
    assert label_tool.coin_at(coins, 300, 300) is None


def test_key_types_cover_all_codes():
    assert sorted(label_tool.KEY_TYPES.values()) == sorted(dataset.LABEL_CODES)
    assert label_tool.KEY_TYPES["1"] == "THB_0_25" and label_tool.KEY_TYPES["6"] == "THB_10"


def test_start_index_skips_labeled(tmp_path):
    data = tmp_path / "data"
    names = ["a.jpg", "b.jpg", "c.jpg"]
    (data / "labels").mkdir(parents=True)
    (data / "labels" / "a.json").write_text("{}", encoding="utf-8")
    assert label_tool.start_index(names, data, None) == 1
    assert label_tool.start_index(names, data, "c.jpg") == 2
    for n in names:
        dataset.label_path(data, n).write_text("{}", encoding="utf-8")
    assert label_tool.start_index(names, data, None) == 0


def test_untyped_counts_missing_types():
    assert label_tool.untyped([{"coin_type": None}, {"coin_type": "unknown"}, {"coin_type": None}]) == 2
