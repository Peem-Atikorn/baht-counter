"""ทดลองว่า Histogram Equalization / CLAHE / White balance ช่วยการหาเหรียญและการจัดกลุ่มสีหรือไม่ (ส่วนที่ 1)

รันจาก root ของ repo (ใช้ชุด tune เท่านั้น ห้ามปรับระบบโดยดูผลชุด test):
    python data/preprocess_experiment.py
    python data/preprocess_experiment.py --split tune web

แต่ละวิธีรันบนภาพเดียวกัน วัด 2 เรื่องแยกกัน
- หาเหรียญ: detect_coins จริงของส่วนที่ 2 บนภาพที่ปรับแล้ว -> Precision, Recall, ความคลาดรัศมี
- จัดกลุ่มสี/ชนิด: classify_coins จริงของส่วนที่ 3 บนวงกลมจากป้ายกำกับ (ตัดผลของการหาเหรียญออก)
  เพื่อดูผลของ white balance ต่อสีอย่างเดียว

ผลเขียนไว้ที่ data/results/preprocess_experiment.{md,json}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "eval")]
from modules.classification import COIN_SPECS, classify_coins  # noqa: E402
from modules.detection import detect_coins  # noqa: E402
from modules.preprocess import preprocess  # noqa: E402
from run_eval import find_image, gt_coins, load_labels, load_splits, match  # noqa: E402

# ชื่อ -> (enhance, white_balance); "clahe" คือวิธีที่ระบบใช้อยู่
VARIANTS = {
    "none": ("none", False),
    "he": ("he", False),
    "clahe": ("clahe", False),
    "clahe+wb": ("clahe", True),
}


def radius_px(c) -> float:
    return c.ellipse[0] / 2 if c.ellipse is not None else c.radius_px


class Tally:
    def __init__(self):
        self.images = self.rejected = 0
        self.gt = self.tp = self.fp = 0
        self.radius_err: list[float] = []
        self.thai = self.group_ok = self.type_ok = 0
        self.seconds: list[float] = []
        self.reasons: dict[str, int] = defaultdict(int)

    def summary(self) -> dict:
        def ratio(a, b):
            return a / b if b else None
        return {
            "images": self.images,
            "rejected": self.rejected,
            "reject_reasons": dict(self.reasons),
            "det_precision": ratio(self.tp, self.tp + self.fp),
            "det_recall": ratio(self.tp, self.gt),
            "radius_err_mean_pct": 100 * float(np.mean(self.radius_err)) if self.radius_err else None,
            "color_group_acc": ratio(self.group_ok, self.thai),
            "coin_type_acc": ratio(self.type_ok, self.thai),
            "preprocess_ms": 1000 * float(np.mean(self.seconds)) if self.seconds else None,
        }


def run_image(bgr: np.ndarray, labels: list[dict], enhance: str, wb: bool, t: Tally):
    t.images += 1
    start = time.perf_counter()
    pre = preprocess(bgr, enhance=enhance, white_balance=wb)
    t.seconds.append(time.perf_counter() - start)
    gt = gt_coins(labels, pre.resize_factor)
    types = [c["coin_type"] for c in labels]
    t.gt += len(gt)
    if pre.status == "failed":
        t.rejected += 1
        t.reasons[pre.reason] += 1
        return

    coins = detect_coins(pre)
    m = match(gt, coins)
    t.tp += len(m)
    t.fp += len(coins) - len(m)
    t.radius_err += [abs(radius_px(coins[j]) - gt[i].radius_px) / gt[i].radius_px for i, j in m.items()]

    res = classify_coins(pre, gt)
    for c, code in zip(res.coins, types):
        if code in COIN_SPECS:
            t.thai += 1
            t.group_ok += c.color_group == COIN_SPECS[code].color_group
            t.type_ok += c.coin_type == code


def evaluate(data: Path, images: list[str], variants: dict = VARIANTS) -> dict[str, dict]:
    tallies = {name: Tally() for name in variants}
    for image in images:
        bgr = cv2.imread(str(find_image(data, image)), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError(f"อ่านภาพ {image} ไม่ได้")
        labels = load_labels(data, image)
        for name, (enhance, wb) in variants.items():
            run_image(bgr, labels, enhance, wb, tallies[name])
    return {name: t.summary() for name, t in tallies.items()}


def fmt(v, pct=False):
    if v is None:
        return "-"
    return f"{100 * v:.1f}" if pct else f"{v:.1f}"


def report(split: str, results: dict[str, dict]) -> str:
    lines = [f"## split: {split}", "",
             "| วิธี | ภาพ | ถูกปฏิเสธ | Det P % | Det R % | คลาดรัศมี % | กลุ่มสีถูก % | ชนิดถูก % | เวลา preprocess (ms) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, s in results.items():
        lines.append(
            f"| {name} | {s['images']} | {s['rejected']} | {fmt(s['det_precision'], True)} "
            f"| {fmt(s['det_recall'], True)} | {fmt(s['radius_err_mean_pct'])} | {fmt(s['color_group_acc'], True)} "
            f"| {fmt(s['coin_type_acc'], True)} | {fmt(s['preprocess_ms'])} |")
    lines += ["", "กลุ่มสี/ชนิดวัดบนวงกลมจากป้ายกำกับ (ไม่ขึ้นกับการหาเหรียญ) · เหรียญ unknown ไม่นับ", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--split", nargs="+", default=["tune"])
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "results")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if "test" in args.split:
        print("! กำลังรันบนชุด test: ใช้รายงานผลได้ แต่ห้ามใช้เลือกวิธีหรือปรับค่า", file=sys.stderr)

    if not (args.data / "splits.csv").exists():
        print(f"! ยังไม่มี {args.data / 'splits.csv'} รัน `python data/dataset.py split` ก่อน", file=sys.stderr)
        return 1
    splits = load_splits(args.data)
    all_results, md = {}, ["# ผลทดลองการปรับปรุงภาพ (ส่วนที่ 1)", "",
                           "เลือกวิธีปรับปรุงภาพจากชุด `tune` เท่านั้น ชุด `test` และ `web` เป็นชุดประเมินผล "
                           "ใช้รายงานอย่างเดียว ห้ามใช้เลือกวิธีหรือปรับค่า", ""]
    for split in args.split:
        images = splits.get(split, [])
        if not images:
            print(f"! split '{split}' ไม่มีภาพ ข้าม", file=sys.stderr)
            continue
        all_results[split] = evaluate(args.data, images)
        text = report(split, all_results[split])
        md.append(text)
        print(text)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "preprocess_experiment.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "preprocess_experiment.md").write_text("\n".join(md), encoding="utf-8")
    print(f"บันทึกผลไว้ที่ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
