"""เปรียบเทียบวิธีการตรวจหาเหรียญ (Detection Baseline Comparison)

รันจาก root ของ repo:
    python eval/detection_baselines.py --split tune
    python eval/detection_baselines.py --split samples

เกณฑ์ประเมิน (docs/plan.md ส่วนที่ 2 และ Issue #2):
    - Proposed: Multi-cue foreground + Distance Transform + Watershed
    - Baseline A (No Watershed): Otsu thresholding + Connected Components (ไม่มี watershed แยกเหรียญติดกัน)
    - Baseline B (K-Means): K-Means clustering บนค่าความสว่างพิกเซล (k=2) + Connected Components
    - Baseline C (Hough Circles): cv2.HoughCircles (Hough Gradient Method)

จับคู่ด้วย match() เกณฑ์เดียวกับ eval/run_eval.py (ระยะจุดศูนย์กลาง <= 0.5 * รัศมีจริง)
บันทึกผลที่ eval/results/detection_baselines_{split}.md และ .json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from modules.detection import detect_coins  # noqa: E402
from modules.preprocess import mock_preprocess, preprocess  # noqa: E402
from schemas import Coin, PreprocessResult  # noqa: E402

MATCH_DIST = 0.5


def load_splits(data: Path) -> dict[str, list[str]]:
    splits: dict[str, list[str]] = defaultdict(list)
    splits_file = data / "splits.csv"
    if splits_file.exists():
        with open(splits_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                splits[row["split"].strip()].append(row["image"].strip())
    return {k: sorted(v) for k, v in splits.items()}


def load_labels(data: Path, image: str) -> list[dict]:
    with open(data / "labels" / f"{Path(image).stem}.json", encoding="utf-8") as f:
        return json.load(f)["coins"]


def find_image(data: Path, image: str) -> Path | None:
    for sub in ("raw", "samples"):
        p = data / sub / image
        if p.exists():
            return p
    return None


def gt_coins(labels: list[dict], k: float) -> list[Coin]:
    return [
        Coin(
            coin_id=i,
            center_xy=(float(c["center_xy"][0] * k), float(c["center_xy"][1] * k)),
            radius_px=float(c["radius_px"] * k),
        )
        for i, c in enumerate(labels)
    ]


def match(gt: list[Coin], pred: list[Coin]) -> dict[int, int]:
    """จับคู่ gt -> pred แบบ greedy ตามระยะ ต้องไม่เกิน MATCH_DIST * รัศมี gt"""
    pairs = []
    for i, g in enumerate(gt):
        for j, p in enumerate(pred):
            d = np.hypot(g.center_xy[0] - p.center_xy[0], g.center_xy[1] - p.center_xy[1])
            if d <= MATCH_DIST * g.radius_px:
                pairs.append((d, i, j))
    used_g, used_p, out = set(), set(), {}
    for _, i, j in sorted(pairs):
        if i not in used_g and j not in used_p:
            out[i] = j
            used_g.add(i)
            used_p.add(j)
    return out


# ---------- Detection Algorithms ----------

def detect_proposed(pre: PreprocessResult) -> list[Coin]:
    """วิธีนำเสนอ: Multi-cue Foreground + Distance Transform + Watershed"""
    return detect_coins(pre)


def detect_no_watershed(pre: PreprocessResult) -> list[Coin]:
    """Baseline A: Otsu Thresholding + Connected Components (ไม่มี Watershed)"""
    gray = pre.gray
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    bw = max(1, int(min(h, w) * 0.02))
    border = np.concatenate([mask[:bw, :].flatten(), mask[-bw:, :].flatten(),
                             mask[:, :bw].flatten(), mask[:, -bw:].flatten()])
    if np.mean(border) > 127:
        mask = cv2.bitwise_not(mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = np.pi * (min(h, w) * 0.02) ** 2
    max_area = np.pi * (min(h, w) * 0.40) ** 2

    coins = []
    cid = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0:
            continue
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity < 0.65:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        coins.append(Coin(coin_id=cid, center_xy=(float(cx), float(cy)), radius_px=float(r)))
        cid += 1
    return coins


def detect_kmeans(pre: PreprocessResult, k: int = 2) -> list[Coin]:
    """Baseline B: K-Means Clustering บนค่าความสว่างพิกเซล + Connected Components"""
    gray = pre.gray
    h, w = gray.shape[:2]
    small = cv2.resize(gray, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    pixels = small.reshape(-1, 1).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    label_img = labels.reshape(small.shape)

    # เลือกกลุ่มที่ไม่ใช่ขอบภาพเป็น foreground
    bw = max(1, int(min(small.shape) * 0.03))
    border = np.concatenate([label_img[:bw, :].flatten(), label_img[-bw:, :].flatten(),
                             label_img[:, :bw].flatten(), label_img[:, -bw:].flatten()])
    bg_label = int(np.bincount(border).argmax())
    fg_label = 1 - bg_label if k == 2 else [i for i in range(k) if i != bg_label][0]

    mask_small = (label_img == fg_label).astype(np.uint8) * 255
    mask = cv2.resize(mask_small, (w, h), interpolation=cv2.INTER_NEAREST)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = np.pi * (min(h, w) * 0.02) ** 2
    max_area = np.pi * (min(h, w) * 0.40) ** 2

    coins = []
    cid = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0:
            continue
        if (4 * np.pi * area / (peri * peri)) < 0.60:
            continue
        (cx, cy), r = cv2.minEnclosingCircle(cnt)
        coins.append(Coin(coin_id=cid, center_xy=(float(cx), float(cy)), radius_px=float(r)))
        cid += 1
    return coins


def detect_hough(pre: PreprocessResult) -> list[Coin]:
    """Baseline C: Hough Gradient Method (cv2.HoughCircles)"""
    gray = pre.gray
    h, w = gray.shape[:2]
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    min_dist = int(min(h, w) * 0.08)
    min_r = int(min(h, w) * 0.03)
    max_r = int(min(h, w) * 0.25)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=min_dist,
        param1=100,
        param2=30,
        minRadius=min_r,
        maxRadius=max_r,
    )
    coins = []
    if circles is not None:
        circles = np.round(circles[0, :]).astype(int)
        for cid, (cx, cy, r) in enumerate(circles):
            coins.append(Coin(coin_id=cid, center_xy=(float(cx), float(cy)), radius_px=float(r)))
    return coins


METHODS = {
    "Proposed (Multi-cue + Watershed)": detect_proposed,
    "Baseline A: No Watershed": detect_no_watershed,
    "Baseline B: K-Means": detect_kmeans,
    "Baseline C: Hough Circles": detect_hough,
}


# ---------- Evaluation Pipeline ----------

def evaluate_baselines(data: Path, images: list[str], preprocess_fn=None) -> dict:
    if preprocess_fn is None:
        try:
            preprocess_fn = preprocess
        except Exception:
            preprocess_fn = mock_preprocess

    valid_images = []
    loaded_data = []

    for img_name in images:
        img_path = find_image(data, img_name)
        if img_path is None:
            continue
        bgr = cv2.imread(str(img_path))
        if bgr is None:
            continue
        try:
            lbl_coins = load_labels(data, img_name)
        except FileNotFoundError:
            continue
        pre = preprocess_fn(bgr)
        k = pre.resize_factor
        gt = gt_coins(lbl_coins, k)
        valid_images.append(img_name)
        loaded_data.append((img_name, pre, gt))

    if not valid_images:
        raise ValueError(f"ไม่พบภาพที่มีไฟล์จริงและป้ายกำกับใน {data}")

    total_gt = sum(len(gt) for _, _, gt in loaded_data)
    results = {}

    for method_name, fn in METHODS.items():
        total_tp = 0
        total_fp = 0
        r_errors = []

        for _, pre, gt in loaded_data:
            if pre.status == "failed":
                pred = []
            else:
                pred = fn(pre)

            m = match(gt, pred)
            tp = len(m)
            fp = len(pred) - tp
            total_tp += tp
            total_fp += fp

            for gi, pi in m.items():
                g_r = gt[gi].radius_px
                p_r = pred[pi].radius_px
                r_errors.append(abs(p_r - g_r) / g_r * 100.0)

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / total_gt if total_gt > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        mean_r_err = float(np.mean(r_errors)) if r_errors else 0.0

        results[method_name] = {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "mean_radius_error_pct": mean_r_err,
            "tp": total_tp,
            "fp": total_fp,
            "gt": total_gt,
        }

    return {
        "images_count": len(valid_images),
        "gt_coins_count": total_gt,
        "images": valid_images,
        "methods": results,
    }


def format_markdown_table(eval_summary: dict, split: str) -> str:
    n_img = eval_summary["images_count"]
    n_gt = eval_summary["gt_coins_count"]
    lines = [
        f"## ผลการเปรียบเทียบ Detection Baselines (Split: {split})",
        f"- จำนวนภาพที่ทดสอบ: {n_img} ภาพ",
        f"- จำนวนเหรียญจริงทั้งหมด (Ground Truth): {n_gt} เหรียญ",
        "",
        "| วิธีการ (Method) | Precision | Recall | F1-Score | Mean Radius Error |",
        "|---|:---:|:---:|:---:|:---:|",
    ]
    for m_name, m_res in eval_summary["methods"].items():
        p = f"{m_res['precision'] * 100:.1f}%"
        r = f"{m_res['recall'] * 100:.1f}%"
        f1 = f"{m_res['f1_score'] * 100:.1f}%"
        err = f"{m_res['mean_radius_error_pct']:.2f}%"
        bold = "**" if "Proposed" in m_name else ""
        lines.append(f"| {bold}{m_name}{bold} | {p} | {r} | {f1} | {err} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="เปรียบเทียบโมเดลตรวจหาเหรียญกับวิธีพื้นฐาน")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="โฟลเดอร์ data")
    parser.add_argument("--split", default="tune", help="split ที่ต้องการประเมิน (เช่น tune, samples)")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results", help="โฟลเดอร์สำหรับบันทึกผล")
    args = parser.parse_args(argv)

    splits = load_splits(args.data)
    if args.split in splits:
        images = splits[args.split]
    elif args.split == "samples":
        samples_dir = args.data / "samples"
        images = [f.name for f in samples_dir.glob("*.jpg")] + [f.name for f in samples_dir.glob("*.png")]
    else:
        # ลองค้นหาจากชื่อ split
        images = [f.name for f in (args.data / "labels").glob("*.json")]

    eval_res = evaluate_baselines(args.data, images)
    md_content = format_markdown_table(eval_res, args.split)

    args.out.mkdir(parents=True, exist_ok=True)
    md_file = args.out / f"detection_baselines_{args.split}.md"
    json_file = args.out / f"detection_baselines_{args.split}.json"

    md_file.write_text(md_content, encoding="utf-8")
    json_file.write_text(json.dumps(eval_res, indent=2, ensure_ascii=False), encoding="utf-8")

    print(md_content)
    print(f"บันทึกผลเรียบร้อย: {md_file} และ {json_file}")


if __name__ == "__main__":
    main()
