"""ตรวจชุดข้อมูลและจัดทำ splits.csv (ส่วนที่ 1)

รันจาก root ของ repo:
    python data/dataset.py check            # ตรวจป้ายกำกับ, splits.csv, จำนวนเหรียญต่อชนิด, ความครบของโปรโตคอล
    python data/dataset.py split            # เพิ่มภาพที่มีป้ายกำกับแล้วแต่ยังไม่อยู่ใน splits.csv
    python data/dataset.py split --dry-run  # ดูก่อนว่าจะจัดภาพไหนไป split ไหน
    python data/dataset.py import labels.zip   # นำเข้าผลที่แก้ในหน้าเว็บ (GET /api/labels/export)

กติกา split
- ภาพที่อยู่ใน splits.csv แล้ว **ไม่ถูกย้าย** (ชุดทดสอบล็อกหลังสัปดาห์ 3) เพิ่มได้แค่ภาพใหม่
- ภาพชื่อ `web_*` -> web, ภาพของทีม -> tune / test
- ภาพของทีมแบ่งตามกลุ่ม (พื้นหลัง, แสง, มุม) จากชื่อไฟล์ ให้ test ได้สัดส่วน --test-frac ในทุกกลุ่ม
  ลำดับในกลุ่มตัดสินด้วย hash ของชื่อไฟล์ จึงได้ผลเดิมทุกครั้ง

รูปแบบชื่อไฟล์และป้ายกำกับ: docs/photo-protocol.md, docs/labels.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from schemas import COIN_TYPES  # noqa: E402

CODES = [t.code for t in COIN_TYPES]
LABEL_CODES = set(CODES) | {"unknown"}
SPLITS = ("tune", "test", "web")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# เป้าตาม docs/plan.md ส่วนที่ 1
MIN_COINS_PER_TYPE = 80
TARGET_TEAM_IMAGES = 150
TARGET_WEB_IMAGES = 30
MIN_BACKGROUNDS = 3
MIN_LIGHTS = 2
COINS_PER_IMAGE = (3, 30)

EXIF_ORIENTATION = 0x0112
SWAPPED_ORIENTATIONS = {5, 6, 7, 8}   # หมุน 90/270 องศา กว้างกับสูงสลับกัน


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def is_web(name: str) -> bool:
    return name.startswith("web_")


def protocol_group(name: str) -> tuple[str, str, str] | None:
    """(พื้นหลัง, แสง, มุม) จากชื่อ <ผู้ถ่าย>_<พื้นหลัง>_<แสง>_<มุม>_<ลำดับ> หรือ None ถ้าชื่อไม่ตรงรูปแบบ"""
    parts = Path(name).stem.split("_")
    if len(parts) != 5 or not parts[4].isdigit():
        return None
    return parts[1], parts[2], parts[3]


def find_images(data: Path) -> dict[str, Path]:
    """ชื่อภาพ -> path ใน raw/ หรือ samples/ (ชื่อซ้ำใช้ raw/ ตามลำดับเดียวกับ eval/run_eval.py)"""
    out: dict[str, Path] = {}
    for sub in ("samples", "raw"):
        d = data / sub
        if d.is_dir():
            out.update({p.name: p for p in d.iterdir() if p.suffix.lower() in IMAGE_EXTS})
    return out


def oriented_size(path: Path) -> tuple[int, int]:
    """(กว้าง, สูง) หลังหมุนตาม EXIF โดยไม่ต้องถอดรหัสทั้งภาพ"""
    with Image.open(path) as img:
        w, h = img.size
        if img.getexif().get(EXIF_ORIENTATION) in SWAPPED_ORIENTATIONS:
            w, h = h, w
    return w, h


def load_splits(data: Path) -> dict[str, str]:
    path = data / "splits.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["image"].strip(): row["split"].strip() for row in csv.DictReader(f)}


def write_splits(data: Path, splits: dict[str, str]):
    with open(data / "splits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["image", "split"])
        for image in sorted(splits):
            w.writerow([image, splits[image]])


def label_path(data: Path, image: str) -> Path:
    return data / "labels" / f"{Path(image).stem}.json"


def check_label(name: str, path: Path, size: tuple[int, int], rep: Report) -> list[str]:
    """ตรวจไฟล์ป้ายกำกับหนึ่งไฟล์ คืนรายการชนิดเหรียญ (ว่างถ้าไฟล์ใช้ไม่ได้)"""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        coins = doc["coins"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        rep.errors.append(f"{path.name}: อ่านไม่ได้ ({e})")
        return []
    w, h = size
    if "image_size" in doc and tuple(doc["image_size"]) != (w, h):
        rep.errors.append(f"{path.name}: image_size {doc['image_size']} ไม่ตรงกับภาพจริง {[w, h]} (หลังหมุนตาม EXIF)")
    types = []
    for k, c in enumerate(coins):
        where = f"{path.name} เหรียญ {k}"
        try:
            (x, y), r, t = c["center_xy"], float(c["radius_px"]), c["coin_type"]
        except (KeyError, TypeError, ValueError):
            rep.errors.append(f"{where}: ต้องมี center_xy [x, y], radius_px, coin_type")
            continue
        if t not in LABEL_CODES:
            rep.errors.append(f"{where}: coin_type ไม่รู้จัก {t!r}")
            continue
        if r <= 0:
            rep.errors.append(f"{where}: radius_px ต้องมากกว่า 0")
            continue
        if not (0 <= x < w and 0 <= y < h):
            rep.errors.append(f"{where}: จุดศูนย์กลาง ({x:.0f}, {y:.0f}) อยู่นอกภาพ {w}x{h}")
            continue
        types.append(t)
    lo, hi = COINS_PER_IMAGE
    if not lo <= len(coins) <= hi and not is_web(name):
        rep.warnings.append(f"{name}: มี {len(coins)} เหรียญ (โปรโตคอลกำหนด {lo}–{hi})")
    return types


def check(data: Path) -> Report:
    rep = Report()
    images = find_images(data)
    label_files = {p.stem: p for p in (data / "labels").glob("*.json")} if (data / "labels").is_dir() else {}
    splits = load_splits(data)

    stems = {Path(n).stem: n for n in images}
    for stem in sorted(set(label_files) - set(stems)):
        rep.errors.append(f"labels/{stem}.json: ไม่พบภาพใน data/raw หรือ data/samples")
    for name in sorted(n for n in images if Path(n).stem not in label_files):
        rep.warnings.append(f"{name}: ยังไม่มีป้ายกำกับ")

    # ตรวจป้ายกำกับทุกภาพ
    types_by_image: dict[str, list[str]] = {}
    for stem, path in sorted(label_files.items()):
        if stem in stems:
            name = stems[stem]
            types_by_image[name] = check_label(name, path, oriented_size(images[name]), rep)

    # splits.csv
    for image, split in sorted(splits.items()):
        if split not in SPLITS:
            rep.errors.append(f"splits.csv: {image} มี split {split!r} (ใช้ได้ {', '.join(SPLITS)})")
        if image not in images:
            rep.errors.append(f"splits.csv: ไม่พบภาพ {image}")
        elif image not in types_by_image:
            rep.errors.append(f"splits.csv: {image} ยังไม่มีป้ายกำกับ")
        if is_web(image) and split != "web":
            rep.errors.append(f"splits.csv: {image} เป็นภาพจากเว็บ ต้องอยู่ใน split web")
    unsplit = sorted(set(types_by_image) - set(splits))
    if unsplit:
        rep.warnings.append(f"มี {len(unsplit)} ภาพที่มีป้ายกำกับแต่ยังไม่อยู่ใน splits.csv (รัน `python data/dataset.py split`)")

    # ชื่อไฟล์ตามโปรโตคอล
    team = [n for n in images if not is_web(n)]
    web = [n for n in images if is_web(n)]
    bad_names = [n for n in team if protocol_group(n) is None]
    for n in bad_names:
        rep.warnings.append(f"{n}: ชื่อไม่ตรงรูปแบบ <ผู้ถ่าย>_<พื้นหลัง>_<แสง>_<มุม>_<ลำดับ> (ภาพเว็บขึ้นต้นด้วย web_)")
    groups = [g for g in map(protocol_group, team) if g]
    if web and not (data / "web_sources.csv").exists():
        rep.warnings.append("มีภาพจากเว็บแต่ไม่มี data/web_sources.csv บันทึกแหล่งที่มา")

    # สรุปจำนวน
    per_type = Counter(t for ts in types_by_image.values() for t in ts)
    per_split: dict[str, Counter] = defaultdict(Counter)
    for name, ts in types_by_image.items():
        per_split[splits.get(name, "(ยังไม่จัด)")].update(ts)
    cols = [s for s in (*SPLITS, "(ยังไม่จัด)") if s in per_split]

    lines = rep.lines
    lines += [f"ภาพของทีม {len(team)} / {TARGET_TEAM_IMAGES} · ภาพจากเว็บ {len(web)} / {TARGET_WEB_IMAGES} "
              f"· มีป้ายกำกับ {len(types_by_image)} ภาพ", ""]
    lines += ["| ชนิด | รวม | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for code in [*CODES, "unknown"]:
        if code == "unknown" and not per_type[code]:
            continue
        mark = "" if code == "unknown" or per_type[code] >= MIN_COINS_PER_TYPE else " ⚠"
        lines.append(f"| {code} | {per_type[code]}{mark} | " + " | ".join(str(per_split[s][code]) for s in cols) + " |")
    lines += ["", f"⚠ = ต่ำกว่าเป้า {MIN_COINS_PER_TYPE} เหรียญต่อชนิด", ""]
    for i, (what, need) in enumerate([("พื้นหลัง", MIN_BACKGROUNDS), ("แสง", MIN_LIGHTS), ("มุม", 2)]):
        seen = Counter(g[i] for g in groups)
        ok = "" if len(seen) >= need else f" ⚠ ต้องมีอย่างน้อย {need} แบบ"
        lines.append(f"- {what}: {dict(sorted(seen.items())) or '-'}{ok}")
    return rep


def assign_splits(data: Path, test_frac: float) -> tuple[dict[str, str], dict[str, str]]:
    """คืน (splits ทั้งหมดหลังเพิ่ม, เฉพาะภาพใหม่ที่เพิ่ม) ภาพเดิมไม่ถูกย้าย"""
    images = find_images(data)
    labelled = sorted(n for n in images if label_path(data, n).exists())
    splits = load_splits(data)
    new = [n for n in labelled if n not in splits]

    added: dict[str, str] = {}
    by_group: dict[object, list[str]] = defaultdict(list)
    for n in new:
        if is_web(n):
            added[n] = "web"
        else:
            by_group[protocol_group(n)].append(n)    # ชื่อไม่ตรงรูปแบบรวมอยู่กลุ่ม None

    for group, names in by_group.items():
        existing = [s for n, s in splits.items() if not is_web(n) and protocol_group(n) == group]
        total = len(existing) + len(names)
        n_test = max(0, round(test_frac * total) - existing.count("test"))
        names.sort(key=lambda n: hashlib.sha1(n.encode()).hexdigest())
        for k, n in enumerate(names):
            added[n] = "test" if k < n_test else "tune"
    return {**splits, **added}, added


def import_export(data: Path, zip_path: Path) -> tuple[list[str], list[str]]:
    """แตก zip จาก GET /api/labels/export ลง raw/ และ labels/ คืน (ภาพที่นำเข้า, ข้อความที่ข้าม)

    ในหน้าเว็บไฟล์ถูกตั้งชื่อด้วย analysis_id จึงเปลี่ยนกลับเป็นชื่อเดิม (`source_filename`) เมื่อชื่อเดิมตรงรูปแบบ
    โปรโตคอลหรือขึ้นต้นด้วย web_ ไม่งั้นใช้ชื่อ analysis_id และ check จะเตือนให้เปลี่ยนชื่อเอง
    ไม่เขียนทับภาพหรือป้ายกำกับที่มีอยู่แล้ว
    """
    (data / "raw").mkdir(parents=True, exist_ok=True)
    (data / "labels").mkdir(parents=True, exist_ok=True)
    existing = {Path(n).stem for n in find_images(data)}
    imported, skipped = [], []
    with zipfile.ZipFile(zip_path) as zf:
        for entry in sorted(n for n in zf.namelist() if n.startswith("labels/") and n.endswith(".json")):
            label = json.loads(zf.read(entry))
            exported = label["image"]
            source = Path(label.get("source_filename") or "").name
            keep_source = source and (protocol_group(source) or is_web(source))
            name = Path(source).stem + Path(exported).suffix if keep_source else exported
            if Path(name).stem in existing or label_path(data, name).exists():
                skipped.append(f"{name}: มีอยู่แล้ว ไม่เขียนทับ")
                continue
            try:
                image_bytes = zf.read(f"raw/{exported}")
            except KeyError:
                skipped.append(f"{exported}: ไม่มีภาพต้นฉบับใน zip")
                continue
            (data / "raw" / name).write_bytes(image_bytes)
            label["image"] = name
            label_path(data, name).write_text(json.dumps(label, ensure_ascii=False, indent=2), encoding="utf-8")
            existing.add(Path(name).stem)
            imported.append(name)
    return imported, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="ตรวจชุดข้อมูล")
    sp = sub.add_parser("split", help="เพิ่มภาพใหม่ลง splits.csv")
    sp.add_argument("--test-frac", type=float, default=0.3, help="สัดส่วนภาพของทีมที่ไป test ในแต่ละกลุ่ม")
    sp.add_argument("--dry-run", action="store_true")
    ip = sub.add_parser("import", help="นำเข้า labels.zip จากหน้าเว็บ")
    ip.add_argument("zip", type=Path)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.cmd == "import":
        imported, skipped = import_export(args.data, args.zip)
        for name in imported:
            print(f"+ {name}")
        for s in skipped:
            print(f"! {s}")
        print(f"นำเข้า {len(imported)} ภาพ · ข้าม {len(skipped)} · ต่อไปรัน `python data/dataset.py check`")
        return 0

    if args.cmd == "check":
        rep = check(args.data)
        print("\n".join(rep.lines))
        for w in rep.warnings:
            print(f"! {w}")
        for e in rep.errors:
            print(f"✗ {e}")
        print(f"\nข้อผิดพลาด {len(rep.errors)} · คำเตือน {len(rep.warnings)}")
        return 1 if rep.errors else 0

    splits, added = assign_splits(args.data, args.test_frac)
    for name, split in sorted(added.items()):
        print(f"{split:5} {name}")
    counts = Counter(splits.values())
    print(f"เพิ่ม {len(added)} ภาพ · รวม " + ", ".join(f"{s} {counts[s]}" for s in SPLITS))
    if not args.dry_run and added:
        write_splits(args.data, splits)
        print(f"บันทึก {args.data / 'splits.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
