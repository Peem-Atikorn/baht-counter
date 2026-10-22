"""วัดเวลาประมวลผลภาพของ POST /api/analyses เทียบเป้าของส่วนที่ 4: < 2 วินาที/ภาพบนเซิร์ฟเวอร์จริง

ใช้:
    cd backend && python scripts/bench.py                              # เซิร์ฟเวอร์ในเครื่อง
    cd backend && python scripts/bench.py --url https://<host> --repeat 5

เวลาแต่ละขั้นอ่านจาก header `Server-Timing` ของแต่ละ request ตรง (ไม่ใช่คำนวณจาก /api/stats ซึ่งเป็นค่าเฉลี่ย
สะสมของทุกผลในเซิร์ฟเวอร์ จึงปนกับผลเก่า/request ของคนอื่นได้) ดู header เดียวกันนี้ใน DevTools ของเบราว์เซอร์
ได้ด้วย (Network → เลือก request → แท็บ Timing)

ไม่ใส่ token หรือข้อมูลส่วนตัวในสคริปต์นี้ — ไม่ต้องมีสิทธิ์พิเศษใดๆ ก็เรียกได้ (ดู docs/backend.md "ไม่มีระบบ login")
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # console เริ่มต้นของ Windows (cp1252) พิมพ์ไทยไม่ได้

WAKEUP_TIMEOUT_SEC = 120
TARGET_SERVER_SEC = 2.0
STAGE_ORDER = ["preprocess", "detection", "classification", "save"]
CONTENT_TYPE_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def parse_server_timing(header: str) -> dict[str, float]:
    """แปลง header `Server-Timing` (รูปแบบมาตรฐาน `name;dur=<ms>`, คั่นด้วย comma) เป็น dict ชื่อขั้น -> วินาที

    ไม่ throw แม้ header ว่าง/ไม่มี/รูปแบบแปลก ๆ (ช่องว่างเกิน, ไม่มี dur) — คืน dict ว่างหรือข้ามรายการนั้นไป
    เพราะเซิร์ฟเวอร์รุ่นเก่าอาจไม่มี header นี้เลย ไม่ควรทำให้สคริปต์ล้ม
    """
    result: dict[str, float] = {}
    if not header or not header.strip():
        return result
    for entry in header.split(","):
        parts = [p.strip() for p in entry.split(";")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        dur_ms: float | None = None
        for param in parts[1:]:
            if "=" not in param:
                continue
            key, _, value = param.partition("=")
            if key.strip() == "dur":
                try:
                    dur_ms = float(value.strip())
                except ValueError:
                    dur_ms = None
        if dur_ms is not None:
            result[name] = dur_ms / 1000.0
    return result


def average_timings(timings_list: list[dict[str, float]]) -> dict[str, float]:
    """เฉลี่ยเวลาแต่ละขั้นจากหลาย request ของภาพเดียวกัน (ข้ามรายการที่ไม่มีขั้นนั้น ไม่ถือเป็น 0)"""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for timings in timings_list:
        for stage, seconds in timings.items():
            sums[stage] = sums.get(stage, 0.0) + seconds
            counts[stage] = counts.get(stage, 0) + 1
    return {stage: sums[stage] / counts[stage] for stage in sums}


def wait_for_health(client: httpx.Client, url: str) -> float:
    """ปลุกเซิร์ฟเวอร์ (sleep บน Render แผน Free) วนเรียก /api/health จนตอบ 200 คืนเวลาที่ใช้ (วินาที)
    เวลานี้ไม่นับรวมในผลวัดเวลาประมวลผล เพราะเป็นเวลา "ตื่น" ของเซิร์ฟเวอร์ ไม่ใช่เวลาประมวลผลภาพ
    """
    start = time.perf_counter()
    deadline = start + WAKEUP_TIMEOUT_SEC
    while time.perf_counter() < deadline:
        try:
            r = client.get(f"{url}/api/health", timeout=10)
            if r.status_code == 200:
                return time.perf_counter() - start
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit(f"เซิร์ฟเวอร์ไม่ตอบ /api/health ภายใน {WAKEUP_TIMEOUT_SEC} วินาที")


def upload_once(client: httpx.Client, url: str, path: Path) -> dict:
    """ส่งภาพเดียวเข้า POST /api/analyses จับเวลาทั้ง request ฝั่ง client — ไม่โยน exception
    เมื่อเจอ 5xx/timeout/ล้มเหลวอื่นๆ เพื่อให้วัดภาพถัดไปต่อได้ (คืน ok=False พร้อมสาเหตุ)
    """
    content_type = CONTENT_TYPE_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")
    data = path.read_bytes()
    t0 = time.perf_counter()
    try:
        r = client.post(
            f"{url}/api/analyses",
            files={"file": (path.name, data, content_type)},
            timeout=60,
        )
    except httpx.HTTPError as exc:
        return {
            "ok": False, "error": f"{type(exc).__name__}: {exc}",
            "request_sec": time.perf_counter() - t0, "server_timing": {},
        }

    elapsed = time.perf_counter() - t0
    if r.status_code != 201:
        return {
            "ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}",
            "request_sec": elapsed, "server_timing": {},
        }

    result = r.json()["result"]
    return {
        "ok": True,
        "request_sec": elapsed,
        "status": result["status"],
        "coin_count": len(result["coins"]),
        "server_timing": parse_server_timing(r.headers.get("server-timing", "")),
    }


def image_resolution(path: Path) -> str:
    img = cv2.imread(str(path))
    if img is None:
        return "?"
    h, w = img.shape[:2]
    return f"{w}x{h}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8000", help="base URL ของเซิร์ฟเวอร์ที่จะวัด")
    parser.add_argument("--images", default="../data/samples", help="โฟลเดอร์ภาพที่ใช้วัด")
    parser.add_argument("--repeat", type=int, default=3, help="จำนวนครั้งที่อัปโหลดภาพเดียวกันซ้ำ")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    images_dir = Path(args.images)
    image_paths = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in CONTENT_TYPE_BY_SUFFIX
    )
    if not image_paths:
        raise SystemExit(f"ไม่พบภาพใน {images_dir}")

    with httpx.Client() as client:
        cold_start_sec = wait_for_health(client, url)
        print(f"ปลุกเซิร์ฟเวอร์: {cold_start_sec:.2f} วินาที (ไม่นับรวมในผลวัดด้านล่าง)\n")

        rows = []
        for path in image_paths:
            request_secs: list[float] = []
            server_timings: list[dict[str, float]] = []
            errors: list[str] = []
            last_ok: dict | None = None
            for _ in range(args.repeat):
                outcome = upload_once(client, url, path)
                request_secs.append(outcome["request_sec"])
                if outcome["ok"]:
                    last_ok = outcome
                    server_timings.append(outcome["server_timing"])
                else:
                    errors.append(outcome["error"])

            rows.append({
                "image": path.name,
                "size_kb": path.stat().st_size / 1024,
                "resolution": image_resolution(path),
                "request_secs": request_secs,
                "status": last_ok["status"] if last_ok else None,
                "coin_count": last_ok["coin_count"] if last_ok else None,
                "errors": errors,
                "stage_secs": average_timings(server_timings),
                "has_timing": any(server_timings),
            })

    stage_names = [s for s in STAGE_ORDER if any(s in row["stage_secs"] for row in rows)]
    extra_stages = sorted({s for row in rows for s in row["stage_secs"]} - set(stage_names))
    stage_names += extra_stages

    col_header = f"{'ภาพ':<28}{'ขนาด':>9}{'ความละเอียด':>14}{'เฉลี่ย(s)':>11}"
    col_header += "".join(f"{s:>16}" for s in stage_names) + f"{'เครือข่าย/อื่นๆ':>16}{'status':>20}{'เหรียญ':>7}"
    print(col_header)
    print("-" * len(col_header))

    any_missing_timing = False
    for row in rows:
        avg_request = sum(row["request_secs"]) / len(row["request_secs"])
        status = row["status"] or f"ERROR x{len(row['errors'])}"
        coins = row["coin_count"] if row["coin_count"] is not None else "-"
        line = f"{row['image']:<28}{row['size_kb']:>7.0f}KB{row['resolution']:>14}{avg_request:>11.2f}"
        if row["has_timing"]:
            for stage in stage_names:
                sec = row["stage_secs"].get(stage)
                line += f"{sec:>16.3f}" if sec is not None else f"{'-':>16}"
            other = avg_request - sum(row["stage_secs"].values())
            line += f"{other:>16.3f}"
        else:
            any_missing_timing = True
            line += "".join(f"{'-':>16}" for _ in stage_names) + f"{'(ไม่มี header)':>16}"
        line += f"{status:>20}{coins!s:>7}"
        print(line)
        for err in row["errors"]:
            print(f"    ! {err}")

    print()
    if any_missing_timing:
        print(
            "คำเตือน: บางภาพไม่มี header Server-Timing กลับมา (เซิร์ฟเวอร์รุ่นเก่า?) "
            "คอลัมน์เวลาแต่ละขั้นของภาพนั้นจึงว่าง\n",
        )

    timed_rows = [row for row in rows if row["has_timing"]]
    if not timed_rows:
        print("ไม่มี request ไหนมี Server-Timing header เลย — วัดเวลาแต่ละขั้นไม่ได้")
        sys.exit(1)

    totals = [sum(row["stage_secs"].values()) for row in timed_rows]
    avg_total = sum(totals) / len(totals)
    print(f"เวลาประมวลผลฝั่งเซิร์ฟเวอร์เฉลี่ยต่อภาพ (รวมทุกขั้นจาก Server-Timing): {avg_total:.3f} วินาที")
    passed = "ผ่าน" if avg_total < TARGET_SERVER_SEC else "ไม่ผ่าน"
    print(f"เป้า < {TARGET_SERVER_SEC:.0f} วินาที: {passed}")


if __name__ == "__main__":
    main()
