"""ประเมินผลทั้งไปป์ไลน์ (ส่วนที่ 3 เป็นเจ้าของ)

รันจาก root ของ repo:
    python eval/run_eval.py                         # ชุด test + web, หาเหรียญด้วยโมดูลส่วนที่ 2
    python eval/run_eval.py --detector gt           # ใช้วงกลมจากป้ายกำกับแทน (วัดเฉพาะการจำแนก)
    python eval/run_eval.py --split tune --dump-colors   # ดูค่า HSV ต่อเหรียญเพื่อปรับเกณฑ์สี

ข้อมูลที่ต้องมี (รูปแบบที่ส่วนที่ 3 ใช้ ถ้าส่วนที่ 1 เปลี่ยน ให้แก้ load_labels)
    data/splits.csv            คอลัมน์ image,split  (split = tune / test / web)
    data/labels/<ชื่อภาพ>.json  {"coins": [{"center_xy": [x, y], "radius_px": r, "coin_type": "THB_1"}, ...]}
                               พิกัดเป็นพิกเซลของภาพต้นฉบับหลังหมุนตาม EXIF
    data/raw/<image> หรือ data/samples/<image>

วิธีที่เปรียบเทียบ
    baseline        สเกลคงที่ค่าเดียว (หาจากชุด tune) เลือกชนิดตามขนาด ไม่ใช้สี
    color+scale     กลุ่มสี + หาสเกลต่อภาพ (วิธีหลัก)
    color+scale+template  เหมือนข้างบน แต่ถ้าสเกลไม่ชัด ใช้ template matching ลวดลาย (template จากชุด tune)
                    หาเหรียญอ้างอิงเองก่อนถามผู้ใช้
    color+scale+1   เหมือน color+scale แต่ถ้าระบบขอ anchor จำลองว่าผู้ใช้กดเลือกชนิดเหรียญ 1 เหรียญ

ผลซ้ำได้ทุกครั้ง (เรียงภาพตามชื่อ ไม่มีการสุ่ม) เขียนไว้ที่ eval/results/
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from modules.classification import (  # noqa: E402
    COIN_CODES, COIN_SPECS, build_templates, classify_coins, classify_coins_baseline, fit_baseline_scale,
)
from modules.classification.color import color_groups  # noqa: E402
from schemas import Coin, CountResult, PreprocessResult  # noqa: E402

GT_ROWS = COIN_CODES + ["unknown"]       # unknown = เหรียญต่างประเทศ/ที่ระลึก
PRED_COLS = COIN_CODES + ["unknown", "none", "missed"]
MATCH_DIST = 0.5        # ถูกเมื่อจุดศูนย์กลางห่างไม่เกินครึ่งรัศมี (docs/plan.md ส่วนที่ 2)


# ---------- โหลดข้อมูล ----------

def load_splits(data: Path) -> dict[str, list[str]]:
    splits: dict[str, list[str]] = defaultdict(list)
    with open(data / "splits.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            splits[row["split"].strip()].append(row["image"].strip())
    return {k: sorted(v) for k, v in splits.items()}


def load_labels(data: Path, image: str) -> list[dict]:
    with open(data / "labels" / f"{Path(image).stem}.json", encoding="utf-8") as f:
        return json.load(f)["coins"]


def find_image(data: Path, image: str) -> Path:
    for sub in ("raw", "samples"):
        p = data / sub / image
        if p.exists():
            return p
    raise FileNotFoundError(f"ไม่พบภาพ {image} ใน data/raw หรือ data/samples")


def get_preprocess():
    """ใช้ preprocess จริงของส่วนที่ 1 ถ้ายังไม่เสร็จใช้ mock_preprocess (ย่อภาพ + ภาพเทา) แทน"""
    from modules.preprocess import mock_preprocess, preprocess
    warned = False

    def run(image: np.ndarray) -> PreprocessResult:
        nonlocal warned
        try:
            return preprocess(image)
        except NotImplementedError:
            if not warned:
                print("! preprocess ยังไม่เสร็จ ใช้ mock_preprocess แทน", file=sys.stderr)
                warned = True
            return mock_preprocess(image)
    return run


def get_detector(name: str):
    if name == "gt":
        return None
    from modules.detection import detect_coins

    def run(pre: PreprocessResult) -> list[Coin]:
        try:
            return detect_coins(pre)
        except NotImplementedError:
            sys.exit("detect_coins ยังไม่เสร็จ ใช้ --detector gt เพื่อวัดเฉพาะการจำแนกไปก่อน")
    return run


def gt_coins(labels: list[dict], k: float) -> list[Coin]:
    return [Coin(coin_id=i, center_xy=(c["center_xy"][0] * k, c["center_xy"][1] * k),
                 radius_px=c["radius_px"] * k) for i, c in enumerate(labels)]


# ---------- จับคู่และวัดผล ----------

def match(gt: list[Coin], pred: list[Coin]) -> dict[int, int]:
    """จับคู่ gt -> pred แบบ greedy ตามระยะ ระยะต้องไม่เกิน MATCH_DIST * รัศมี gt"""
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


def simulate_anchor(pre, coins, res: CountResult, gt_types, m) -> CountResult:
    """จำลองผู้ใช้กดเลือกชนิดเหรียญ 1 เหรียญ (เหรียญแรกที่ยังไม่มีชนิดและป้ายกำกับเป็นเหรียญไทย)"""
    if res.scale_mm_per_px is not None:
        return res
    inv = {j: i for i, j in m.items()}
    for j, c in enumerate(res.coins):
        if c.coin_type is None and j in inv and gt_types[inv[j]] in COIN_SPECS:
            return classify_coins(pre, coins, anchor=(c.coin_id, gt_types[inv[j]]))
    return res


class Stats:
    def __init__(self):
        self.conf = defaultdict(Counter)   # gt -> pred
        self.fp = 0
        self.images = 0
        self.exact = 0
        self.undecided = 0
        self.needs_conf = 0
        self.failed = 0
        self.abs_err: list[float] = []

    def add(self, gt_types, gt_total, res: CountResult, m: dict[int, int]):
        self.images += 1
        for i, t in enumerate(gt_types):
            if i not in m:
                self.conf[t]["missed"] += 1
            else:
                p = res.coins[m[i]].coin_type
                self.conf[t][p if p is not None else "none"] += 1
        self.fp += len(res.coins) - len(m)
        self.needs_conf += res.status == "needs_confirmation"
        self.failed += res.status == "failed"
        if res.total_baht is None:
            self.undecided += 1
        else:
            err = abs(res.total_baht - gt_total)
            self.abs_err.append(err)
            self.exact += err < 0.005

    def summary(self) -> dict:
        n = sum(sum(r.values()) for r in self.conf.values())
        correct = sum(self.conf[t][t] for t in self.conf)
        tp = n - sum(r["missed"] for r in self.conf.values())
        return {
            "images": self.images,
            "gt_coins": n,
            "det_precision": tp / (tp + self.fp) if tp + self.fp else None,
            "det_recall": tp / n if n else None,
            "coin_accuracy": correct / n if n else None,
            "coin_accuracy_detected": correct / tp if tp else None,
            "total_exact_pct": 100 * self.exact / self.images if self.images else None,
            "total_mae_baht": float(np.mean(self.abs_err)) if self.abs_err else None,
            "total_undecided_pct": 100 * self.undecided / self.images if self.images else None,
            "needs_confirmation_pct": 100 * self.needs_conf / self.images if self.images else None,
            "failed_pct": 100 * self.failed / self.images if self.images else None,
            "confusion": {t: dict(self.conf[t]) for t in GT_ROWS if t in self.conf},
        }


# ---------- รายงาน ----------

def fmt(v, pct=False):
    if v is None:
        return "-"
    return f"{v:.1f}" if pct else f"{v:.3f}"


def report(split: str, detector: str, results: dict[str, dict]) -> str:
    lines = [f"## split: {split} (detector: {detector})", "",
             "| วิธี | ภาพ | เหรียญ | Det P | Det R | Acc รายเหรียญ | Acc (เฉพาะที่หาเจอ) "
             "| ยอดถูกพอดี % | MAE ยอด (บาท) | ยอดระบุไม่ได้ % | ต้องยืนยัน % | ล้มเหลว % |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, s in results.items():
        lines.append(
            f"| {name} | {s['images']} | {s['gt_coins']} | {fmt(s['det_precision'])} | {fmt(s['det_recall'])} "
            f"| {fmt(s['coin_accuracy'])} | {fmt(s['coin_accuracy_detected'])} "
            f"| {fmt(s['total_exact_pct'], True)} | {fmt(s['total_mae_baht'])} "
            f"| {fmt(s['total_undecided_pct'], True)} | {fmt(s['needs_confirmation_pct'], True)} "
            f"| {fmt(s['failed_pct'], True)} |")
    for name, s in results.items():
        lines += ["", f"### confusion matrix: {name} (แถว = ป้ายกำกับ, คอลัมน์ = ผลระบบ)", "",
                  "| | " + " | ".join(PRED_COLS) + " |", "|---" * (len(PRED_COLS) + 1) + "|"]
        for t in GT_ROWS:
            row = s["confusion"].get(t, {})
            lines.append(f"| {t} | " + " | ".join(str(row.get(c, 0)) for c in PRED_COLS) + " |")
    return "\n".join(lines) + "\n"


# ---------- main ----------

def prepare(data: Path, image: str, preprocess, detect):
    labels = load_labels(data, image)
    bgr = cv2.imread(str(find_image(data, image)), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"อ่านภาพ {image} ไม่ได้")
    pre = preprocess(bgr)
    k = pre.resize_factor
    gt = gt_coins(labels, k)
    gt_types = [c["coin_type"] for c in labels]
    if pre.status == "failed":
        coins = []
    elif detect is None:
        coins = [c.model_copy() for c in gt]
    else:
        coins = detect(pre)
    return pre, gt, gt_types, coins


def learn_from_tune(data: Path, images: list[str], preprocess):
    """จากชุดปรับระบบเท่านั้น: สเกลคงที่ของวิธีพื้นฐาน และ template ลวดลายของแต่ละชนิด"""
    diams, types, samples = [], [], []
    for image in images:
        pre, gt, gt_types, _ = prepare(data, image, preprocess, None)
        diams += [2 * c.radius_px for c in gt]
        types += gt_types
        if pre.status != "failed":
            samples += [(pre.gray, c, t) for c, t in zip(gt, gt_types) if t in COIN_SPECS]
    return fit_baseline_scale(diams, types), build_templates(samples)


def dump_colors(data: Path, images: list[str], preprocess, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["image", "coin_index", "gt_type", "group", "inner_h", "inner_s", "inner_v",
                    "ring_h", "ring_s", "ring_v"])
        for image in images:
            pre, gt, gt_types, _ = prepare(data, image, preprocess, None)
            if pre.status == "failed":
                continue
            for i, f_ in enumerate(color_groups(pre.image, gt)):
                w.writerow([image, i, gt_types[i], f_.group, *(f_.inner_hsv or ("",) * 3),
                            *(f_.ring_hsv or ("",) * 3)])
    print(f"เขียนค่าสีไว้ที่ {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--split", nargs="+", default=["test", "web"])
    ap.add_argument("--tune-split", default="tune", help="split ที่ใช้หาสเกลคงที่ของวิธีพื้นฐาน")
    ap.add_argument("--detector", choices=["pipeline", "gt"], default="pipeline")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    ap.add_argument("--dump-colors", action="store_true", help="เขียน HSV ต่อเหรียญเป็น CSV แล้วจบ")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    splits = load_splits(args.data)
    preprocess = get_preprocess()

    if args.dump_colors:
        for split in args.split:
            dump_colors(args.data, splits.get(split, []), preprocess, args.out / f"colors_{split}.csv")
        return

    detect = get_detector(args.detector)
    if not splits.get(args.tune_split):
        sys.exit(f"ไม่มีภาพใน split '{args.tune_split}' สำหรับหาสเกลของวิธีพื้นฐาน")
    base_scale, templates = learn_from_tune(args.data, splits[args.tune_split], preprocess)
    n_templates = {k: len(v) for k, v in sorted(templates.items())}
    print(f"สเกลคงที่ของวิธีพื้นฐาน: {base_scale:.5f} มม./พิกเซล")
    print(f"template ลวดลายจากชุด {args.tune_split}: {n_templates}")

    args.out.mkdir(parents=True, exist_ok=True)
    all_results = {"baseline_mm_per_px": base_scale, "templates": n_templates,
                   "detector": args.detector, "splits": {}}
    md = [f"# ผลประเมิน (detector: {args.detector})", "",
          f"วิธีพื้นฐานใช้สเกลคงที่ {base_scale:.5f} มม./พิกเซล จากชุด {args.tune_split}",
          f"template ลวดลายจากชุด {args.tune_split}: {n_templates}", ""]
    for split in args.split:
        images = splits.get(split, [])
        if not images:
            print(f"! split '{split}' ไม่มีภาพ ข้าม", file=sys.stderr)
            continue
        stats = {k: Stats() for k in ("baseline", "color+scale", "color+scale+template", "color+scale+1")}
        for image in images:
            pre, gt, gt_types, coins = prepare(args.data, image, preprocess, detect)
            gt_total = sum(COIN_SPECS[t].value_baht for t in gt_types if t in COIN_SPECS)
            m = match(gt, coins)
            res_b = classify_coins_baseline(pre, coins, base_scale)
            res_c = classify_coins(pre, coins)
            res_t = classify_coins(pre, coins, templates=templates)
            res_a = simulate_anchor(pre, coins, res_c, gt_types, m)
            stats["baseline"].add(gt_types, gt_total, res_b, m)
            stats["color+scale"].add(gt_types, gt_total, res_c, m)
            stats["color+scale+template"].add(gt_types, gt_total, res_t, m)
            stats["color+scale+1"].add(gt_types, gt_total, res_a, m)
        summ = {k: v.summary() for k, v in stats.items()}
        all_results["splits"][split] = summ
        text = report(split, args.detector, summ)
        md.append(text)
        print(text)

    (args.out / f"results_{args.detector}.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / f"results_{args.detector}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"บันทึกผลไว้ที่ {args.out}")


if __name__ == "__main__":
    main()
