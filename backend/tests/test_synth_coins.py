"""ภาพสังเคราะห์เหรียญหายาก data/synth_coins.py (ส่วนที่ 1) และการจัด split ของภาพ synth_*"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))
import dataset  # noqa: E402
import synth_coins  # noqa: E402

BG = 120
COIN_COLORS = {"THB_1": (200, 200, 205), "THB_2": (210, 170, 60), "THB_10": (190, 160, 90)}


def coin_image(coins, size=(800, 600)):
    img = np.full((size[1], size[0], 3), BG, np.uint8)
    for c in coins:
        cv2.circle(img, tuple(int(v) for v in c["center_xy"]), int(c["radius_px"]), COIN_COLORS[c["coin_type"]], -1)
    return img


def add_labelled(data: Path, name: str, coins, split="tune"):
    (data / "raw").mkdir(parents=True, exist_ok=True)
    (data / "labels").mkdir(exist_ok=True)
    Image.fromarray(coin_image(coins)).save(data / "raw" / name)
    (data / "labels" / f"{Path(name).stem}.json").write_text(json.dumps({"coins": coins}), encoding="utf-8")
    splits = dataset.load_splits(data)
    splits[name] = split
    dataset.write_splits(data, splits)


def test_paste_coins_uses_base_scale_and_free_space():
    base_coins = [{"center_xy": [100, 100], "radius_px": 40, "coin_type": "THB_1"},      # 20 มม. -> 0.25 มม./px
                  {"center_xy": [250, 100], "radius_px": synth_coins.DIAMETER_MM["THB_10"] * 2, "coin_type": "THB_10"}]  # 0.25 มม./px เท่ากัน
    base = coin_image(base_coins)
    src_coins = [{"center_xy": [300, 300], "radius_px": 60, "coin_type": "THB_2"}]
    cut = synth_coins.cut_coin(coin_image(src_coins), (300, 300), 60, "src.jpg", 0)

    img, added = synth_coins.paste_coins(base, base_coins, [cut], 4, "THB_2", np.random.default_rng(1))
    assert len(added) == 4
    assert base[300, 400].tolist() == [BG] * 3            # ไม่แก้ภาพที่ส่งเข้ามา
    expected_r = synth_coins.DIAMETER_MM["THB_2"] / 2 / (20 / 80)
    circles = [(c["center_xy"], c["radius_px"]) for c in base_coins + added]
    for c in added:
        (x, y), r = c["center_xy"], c["radius_px"]
        assert math.isclose(r, expected_r, abs_tol=0.1)
        assert img[int(y), int(x)].tolist() == list(COIN_COLORS["THB_2"])
        assert c["synthetic"]["source"] == "src.jpg"
        for (ox, oy), orad in circles:
            if (ox, oy) != (x, y):
                assert math.hypot(x - ox, y - oy) >= r + orad - 0.2   # ไม่ทับเหรียญอื่น


def test_paste_coins_without_known_scale_adds_nothing():
    base = coin_image([])
    cut = synth_coins.cut_coin(coin_image([{"center_xy": [300, 300], "radius_px": 60, "coin_type": "THB_2"}]),
                               (300, 300), 60, "src.jpg", 0)
    img, added = synth_coins.paste_coins(base, [], [cut], 3, "THB_2", np.random.default_rng(0))
    assert added == [] and (img == base).all()


def test_main_writes_synth_images_that_split_to_synth_and_skip_test_sources(tmp_path):
    two = {"center_xy": [600, 300], "radius_px": 44, "coin_type": "THB_2"}
    one = {"center_xy": [150, 150], "radius_px": 40, "coin_type": "THB_1"}
    add_labelled(tmp_path, "p1_white_room_top_001.jpg", [one, two])
    add_labelled(tmp_path, "p1_white_room_top_002.jpg", [one])
    add_labelled(tmp_path, "p1_white_room_top_003.jpg", [one, two], split="test")    # ห้ามใช้เป็นต้นทาง/ภาพฐาน
    add_labelled(tmp_path, "p1_white_room_tilt15_004.jpg", [one, two])               # มุมเอียง ไม่ใช้

    assert synth_coins.main(["--data", str(tmp_path), "--count", "3", "--per-image", "2", "2"]) == 0
    made = sorted(p.name for p in (tmp_path / "raw").glob("synth_*"))
    assert made == [f"synth_white_room_top_{k:03d}.jpg" for k in (1, 2, 3)]
    for name in made:
        label = json.loads(dataset.label_path(tmp_path, name).read_text(encoding="utf-8"))
        assert label["synthetic"]["base"] in {"p1_white_room_top_001.jpg", "p1_white_room_top_002.jpg"}
        assert {c["synthetic"]["source"] for c in label["coins"] if "synthetic" in c} == {"p1_white_room_top_001.jpg"}

    dataset.main(["--data", str(tmp_path), "split"])
    splits = dataset.load_splits(tmp_path)
    assert all(splits[n] == "synth" for n in made)
    rep = dataset.check(tmp_path)
    assert not rep.errors
    thb2 = next(line for line in rep.lines if line.startswith("| THB_2 |"))
    assert thb2.startswith("| THB_2 | 3 ⚠ |")     # รวมนับเฉพาะภาพจริง (001, 003, tilt15) ไม่นับ synth


def test_check_rejects_synth_image_outside_synth_split(tmp_path):
    add_labelled(tmp_path, "synth_white_room_top_001.jpg",
                 [{"center_xy": [150, 150], "radius_px": 40, "coin_type": "THB_1"}], split="tune")
    assert any("synth" in e for e in dataset.check(tmp_path).errors)
