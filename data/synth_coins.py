"""สร้างภาพสังเคราะห์เพิ่มเหรียญชนิดที่หายาก (ส่วนที่ 1) ค่าเริ่มต้นคือ 2 บาท

รันจาก root ของ repo:
    python data/synth_coins.py --count 20            # สร้าง 20 ภาพลง data/raw + data/labels
    python data/synth_coins.py --count 20 --dry-run  # ดูว่าจะวางเหรียญกี่เหรียญ ไม่เขียนไฟล์
    python data/dataset.py split                     # ภาพ synth_* ไป split synth เสมอ

วิธีทำ (อธิบายได้ทีละขั้น ไม่ใช้โมเดล)
1. ตัดเหรียญ 2 บาทจากภาพจริงในชุด tune ตามวงในป้ายกำกับ (เฉพาะภาพมุมตรง)
2. เลือกภาพฐานมุมตรงในชุด tune ที่พื้นหลังเดียวกับเหรียญต้นทาง แล้วหาสเกล มม./พิกเซล จากเหรียญที่มีป้ายในภาพฐาน
3. ย่อ/ขยายเหรียญให้ได้ขนาดจริงตามสเกลของภาพฐาน หมุนแบบสุ่ม (ไม่กลับด้าน เพราะเหรียญจริงไม่มีลายกลับด้าน)
   ปรับความสว่างตามพื้นหลังรอบจุดที่วาง แล้ววางด้วยหน้ากากวงกลมขอบนุ่ม บนพื้นที่ว่างที่ไม่ทับเหรียญเดิม

ข้อจำกัด: เหรียญที่วางไม่มีเงา และเป็นเหรียญจริงชุดเดิมที่หมุนซ้ำ ไม่ได้เพิ่มความหลากหลายของสีหรือลาย
ห้ามใช้แทนภาพจริงในชุดทดสอบ (dataset.py จัดภาพ synth_* ไว้ใน split synth แยกจาก tune/test)
ไม่ใช้ภาพในชุด test เป็นทั้งต้นทางและภาพฐาน กันข้อมูลชุดทดสอบรั่วเข้ามา
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset  # noqa: E402
from dataset import COIN_TYPES, ROOT  # noqa: E402

DIAMETER_MM = {t.code: t.diameter_mm for t in COIN_TYPES}
MASK_EDGE = 1.03         # ขอบหน้ากาก (เท่าของรัศมีป้าย) ขอบเหรียญจริงอยู่นอกวงป้ายเล็กน้อย (วัดจากภาพ tune: มัธยฐาน 1.025–1.033)
                         # ถ้าตัดในวงป้ายจะเสียขอบเหรียญ เหรียญที่วางเห็นเล็กกว่าเหรียญจริงในภาพเดียวกัน
FEATHER = 0.02           # ความนุ่มของขอบหน้ากาก (สัดส่วนของรัศมี)
BG_RING = (1.15, 1.45)   # วงแหวนรอบเหรียญที่ใช้วัดความสว่างพื้นหลัง (เท่าของรัศมี)
GAIN_RANGE = (0.8, 1.25) # ปรับความสว่างได้ไม่เกินช่วงนี้ ภาพฐานกับต้นทางแสงต่างกันมากกว่านี้ไม่ใช้
MAX_GAP = 0.3            # ระยะห่างจากเหรียญเดิมสุ่ม 0..MAX_GAP เท่าของรัศมี (0 = ชิดกันพอดี ใช้ทดสอบ watershed)
MAX_BG_STD = 18.0        # จุดวางที่พื้นหลังไม่เรียบกว่านี้ (ค่าเบี่ยงเบนของภาพเทา) ข้าม เช่น ขอบกระดาษหรือของอื่นในภาพ
TRIES_PER_COIN = 200


@dataclass
class Cutout:
    rgb: np.ndarray          # สี่เหลี่ยมรอบเหรียญ รวมวงแหวนพื้นหลัง
    center: tuple[float, float]   # จุดศูนย์กลางเหรียญในพิกัดของ rgb
    radius: float
    bg_level: float          # ความสว่างพื้นหลังรอบเหรียญในภาพต้นทาง
    source: str
    index: int               # ลำดับเหรียญในป้ายของภาพต้นทาง


def gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def ring_level(g: np.ndarray, center: tuple[float, float], radius: float,
               exclude: list[tuple[float, float, float]] = ()) -> tuple[float, float]:
    """(มัธยฐาน, ค่าเบี่ยงเบน) ของภาพเทาในวงแหวน BG_RING รอบจุด ใช้วัดพื้นหลังรอบเหรียญ

    exclude = เหรียญ (x, y, r) ที่ไม่นับในวงแหวน (ตัดถึง BG_RING[0] เท่าของรัศมี รวมขอบและเงา)
    ถ้าเหลือพื้นหลังไม่ถึงครึ่งวงแหวน คืนค่าเบี่ยงเบน inf
    """
    h, w = g.shape
    x0, x1 = max(0, int(center[0] - radius * BG_RING[1])), min(w, int(center[0] + radius * BG_RING[1]) + 1)
    y0, y1 = max(0, int(center[1] - radius * BG_RING[1])), min(h, int(center[1] + radius * BG_RING[1]) + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(xx - center[0], yy - center[1])
    ring = (d >= radius * BG_RING[0]) & (d <= radius * BG_RING[1])
    keep = ring.copy()
    for ex, ey, er in exclude:
        keep &= np.hypot(xx - ex, yy - ey) > er * BG_RING[0]
    vals = g[y0:y1, x0:x1][keep]
    if vals.size == 0 or vals.size < ring.sum() / 2:
        return 0.0, math.inf
    return float(np.median(vals)), float(vals.std())


def cut_coin(rgb: np.ndarray, center: tuple[float, float], radius: float, source: str, index: int) -> Cutout:
    half = int(math.ceil(radius * BG_RING[1])) + 2
    cx, cy = center
    x0, y0 = max(0, int(cx) - half), max(0, int(cy) - half)
    crop = rgb[y0:int(cy) + half + 1, x0:int(cx) + half + 1].copy()
    local = (cx - x0, cy - y0)
    level, _ = ring_level(gray(crop), local, radius)
    return Cutout(crop, local, radius, level, source, index)


def scale_mm_per_px(coins: list[dict]) -> float | None:
    """สเกลของภาพจากเหรียญที่มีป้าย (มัธยฐานของ เส้นผ่านศูนย์กลางจริง / เส้นผ่านศูนย์กลางพิกเซล)"""
    vals = [DIAMETER_MM[c["coin_type"]] / (2 * float(c["radius_px"])) for c in coins if c["coin_type"] in DIAMETER_MM]
    return float(np.median(vals)) if vals else None


def render_coin(cut: Cutout, radius: float, angle: float, gain: float) -> tuple[np.ndarray, np.ndarray]:
    """(ภาพเหรียญ float32, หน้ากาก 0..1) ขนาด S×S ศูนย์กลางอยู่กลางภาพ หมุน angle องศาและย่อให้ได้รัศมี radius"""
    size = 2 * int(math.ceil(radius * (MASK_EDGE + FEATHER))) + 5
    m = cv2.getRotationMatrix2D(cut.center, angle, radius / cut.radius)
    m[:, 2] += (size / 2 - cut.center[0], size / 2 - cut.center[1])
    coin = cv2.warpAffine(cut.rgb, m, (size, size), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx + 0.5 - size / 2, yy + 0.5 - size / 2)
    soft = max(1.0, FEATHER * radius)
    mask = np.clip((radius * MASK_EDGE - d) / soft + 0.5, 0, 1).astype(np.float32)
    return coin.astype(np.float32) * gain, mask


def paste_coins(base: np.ndarray, coins: list[dict], cutouts: list[Cutout], n: int, code: str,
                rng: np.random.Generator) -> tuple[np.ndarray, list[dict]]:
    """วางเหรียญชนิด code เพิ่ม n เหรียญ (หรือน้อยกว่าถ้าไม่มีที่ว่าง) คืน (ภาพใหม่, ป้ายของเหรียญที่วาง)

    ฟังก์ชันบริสุทธิ์ ไม่แก้ base และ coins ที่ส่งเข้ามา
    """
    scale = scale_mm_per_px(coins)
    if scale is None or not cutouts:
        return base.copy(), []
    radius = DIAMETER_MM[code] / 2 / scale
    out = base.astype(np.float32)
    g = gray(base)
    h, w = g.shape
    taken = [(float(c["center_xy"][0]), float(c["center_xy"][1]), float(c["radius_px"])) for c in coins]
    margin = radius * BG_RING[1] + 2
    added: list[dict] = []
    for _ in range(n):
        for _ in range(TRIES_PER_COIN):
            x, y = rng.uniform(margin, w - margin), rng.uniform(margin, h - margin)
            gap = rng.uniform(0, MAX_GAP) * radius
            if any(math.hypot(x - tx, y - ty) < (tr + radius) * MASK_EDGE + gap for tx, ty, tr in taken):
                continue
            # ไม่นับเหรียญเดิมและเหรียญที่เพิ่งวางในวงแหวน ให้วางชิดได้ทั้งเหรียญจริงและเหรียญสังเคราะห์
            level, spread = ring_level(g, (x, y), radius, taken)
            if spread > MAX_BG_STD:
                continue
            cut = cutouts[rng.integers(len(cutouts))]
            gain = level / cut.bg_level if cut.bg_level > 0 else 1.0
            if not GAIN_RANGE[0] <= gain <= GAIN_RANGE[1]:
                continue
            angle = float(rng.uniform(0, 360))
            coin, mask = render_coin(cut, radius, angle, gain)
            size = coin.shape[0]
            x0, y0 = int(round(x - size / 2)), int(round(y - size / 2))
            region = out[y0:y0 + size, x0:x0 + size]
            region[:] = region * (1 - mask[..., None]) + coin * mask[..., None]
            taken.append((x, y, radius))
            added.append({"center_xy": [round(x, 1), round(y, 1)], "radius_px": round(radius, 1), "coin_type": code,
                          "synthetic": {"source": cut.source, "source_coin": cut.index, "angle_deg": round(angle, 1),
                                        "gain": round(gain, 3)}})
            break
    return np.clip(out, 0, 255).astype(np.uint8), added


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(ImageOps.exif_transpose(img).convert("RGB"))


def load_label(data: Path, image: str) -> dict:
    return json.loads(dataset.label_path(data, image).read_text(encoding="utf-8"))


def candidates(data: Path) -> list[str]:
    """ภาพจริงมุมตรงในชุด tune ที่มีป้ายแล้ว (ต้นทางและภาพฐาน)"""
    splits = dataset.load_splits(data)
    return sorted(n for n, s in splits.items()
                  if s == "tune" and (g := dataset.protocol_group(n)) and g[2] == "top"
                  and dataset.label_path(data, n).exists())


def next_seq(data: Path) -> int:
    seqs = [int(p.stem.rsplit("_", 1)[1]) for p in (data / "raw").glob("synth_*")
            if p.stem.rsplit("_", 1)[1].isdigit()] if (data / "raw").is_dir() else []
    return max(seqs, default=0) + 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--coin", default="THB_2", choices=sorted(DIAMETER_MM))
    ap.add_argument("--count", type=int, default=20, help="จำนวนภาพที่สร้าง")
    ap.add_argument("--per-image", type=int, nargs=2, default=(3, 6), metavar=("MIN", "MAX"),
                    help="จำนวนเหรียญที่วางต่อภาพ (สุ่มในช่วงนี้)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    images = dataset.find_images(args.data)
    pool = [n for n in candidates(args.data) if n in images]
    labels = {n: load_label(args.data, n) for n in pool}
    sources = [n for n in pool if any(c["coin_type"] == args.coin for c in labels[n]["coins"])]
    if not sources:
        print(f"ไม่มีภาพมุมตรงในชุด tune ที่มีเหรียญ {args.coin} ใช้เป็นต้นทาง", file=sys.stderr)
        return 1

    # เหรียญต้นทางแยกตามพื้นหลัง วางบนพื้นหลังเดียวกันเท่านั้น ไม่งั้นขอบพื้นหลังเดิมที่ติดมาจะเห็นเป็นวง
    cut_by_bg: dict[str, list[Cutout]] = {}
    for n in sources:
        rgb = load_rgb(images[n])
        for k, c in enumerate(labels[n]["coins"]):
            if c["coin_type"] == args.coin:
                cut = cut_coin(rgb, tuple(c["center_xy"]), float(c["radius_px"]), n, k)
                cut_by_bg.setdefault(dataset.protocol_group(n)[0], []).append(cut)
    bases = [n for n in pool if dataset.protocol_group(n)[0] in cut_by_bg]
    print(f"เหรียญต้นทาง {sum(map(len, cut_by_bg.values()))} เหรียญจาก {len(sources)} ภาพ · ภาพฐาน {len(bases)} ภาพ")

    rng = np.random.default_rng(args.seed)
    seq = next_seq(args.data)
    total = 0
    for i in range(args.count):
        base_name = bases[rng.integers(len(bases))]
        bg, light, angle = dataset.protocol_group(base_name)
        n = int(rng.integers(args.per_image[0], args.per_image[1] + 1))
        if args.dry_run:
            print(f"(dry-run) จาก {base_name} วางสูงสุด {n} เหรียญ")
            continue
        label = labels[base_name]
        img, added = paste_coins(load_rgb(images[base_name]), label["coins"], cut_by_bg[bg], n, args.coin, rng)
        if not added:
            print(f"! {base_name}: ไม่มีที่ว่างพอ ข้าม")
            continue
        name = f"synth_{bg}_{light}_{angle}_{seq:03d}.jpg"
        seq += 1
        Image.fromarray(img).save(args.data / "raw" / name, quality=92)
        out = {"image": name, "image_size": [img.shape[1], img.shape[0]], "coins": label["coins"] + added,
               "notes": f"ภาพสังเคราะห์จาก {base_name} วาง {args.coin} เพิ่ม {len(added)} เหรียญ (data/synth_coins.py)",
               "synthetic": {"base": base_name, "coin": args.coin, "seed": args.seed}}
        dataset.label_path(args.data, name).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        total += len(added)
        print(f"+ {name}  จาก {base_name}  วาง {len(added)} เหรียญ")
    if not args.dry_run:
        print(f"วาง {args.coin} รวม {total} เหรียญ · ต่อไปรัน `python data/dataset.py split` แล้ว `check`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
