"""วัดเวลาประมวลผลภาพของ POST /api/analyses เทียบเป้าของส่วนที่ 4: < 2 วินาที/ภาพบนเซิร์ฟเวอร์จริง

ใช้:
    cd backend && python scripts/bench.py                              # เซิร์ฟเวอร์ในเครื่อง
    cd backend && python scripts/bench.py --url https://<host> --repeat 5

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
CONTENT_TYPE_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


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


def get_stats(client: httpx.Client, url: str) -> dict:
    r = client.get(f"{url}/api/stats", timeout=30)
    r.raise_for_status()
    return r.json()


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
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "request_sec": time.perf_counter() - t0}

    elapsed = time.perf_counter() - t0
    if r.status_code != 201:
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}", "request_sec": elapsed}

    result = r.json()["result"]
    return {
        "ok": True,
        "request_sec": elapsed,
        "status": result["status"],
        "coin_count": len(result["coins"]),
    }


def stage_seconds_for_round(before: dict, after: dict) -> dict[str, float]:
    """avg_timings_sec ใน /api/stats สะสมมาตั้งแต่ก่อนรอบวัดนี้ (ผลเก่าที่มีอยู่แล้วในเซิร์ฟเวอร์)
    คำนวณเฉลี่ยเฉพาะของรอบนี้จากผลต่างของผลรวม (avg * count) ก่อน/หลัง
    """
    n_before, n_after = before["analyses_count"], after["analyses_count"]
    n_round = n_after - n_before
    if n_round <= 0:
        return {}
    stages: dict[str, float] = {}
    for stage, avg_after in after["avg_timings_sec"].items():
        avg_before = before["avg_timings_sec"].get(stage, 0.0)
        stages[stage] = (avg_after * n_after - avg_before * n_before) / n_round
    return stages


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

        stats_before = get_stats(client, url)

        rows = []
        for path in image_paths:
            request_secs: list[float] = []
            errors: list[str] = []
            last_ok: dict | None = None
            for _ in range(args.repeat):
                outcome = upload_once(client, url, path)
                request_secs.append(outcome["request_sec"])
                if outcome["ok"]:
                    last_ok = outcome
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
            })

        stats_after = get_stats(client, url)

    stage_secs = stage_seconds_for_round(stats_before, stats_after)

    header = f"{'ภาพ':<28}{'ขนาด':>9}{'ความละเอียด':>14}{'เฉลี่ย(s)':>11}{'สูงสุด(s)':>11}{'status':>20}{'เหรียญ':>7}"
    print(header)
    print("-" * len(header))
    for row in rows:
        avg = sum(row["request_secs"]) / len(row["request_secs"])
        worst = max(row["request_secs"])
        status = row["status"] or f"ERROR x{len(row['errors'])}"
        coins = row["coin_count"] if row["coin_count"] is not None else "-"
        print(
            f"{row['image']:<28}{row['size_kb']:>7.0f}KB{row['resolution']:>14}"
            f"{avg:>11.2f}{worst:>11.2f}{status:>20}{coins!s:>7}",
        )
        for err in row["errors"]:
            print(f"    ! {err}")

    print()
    if not stage_secs:
        print("ไม่มีผลใหม่ใน /api/stats รอบนี้ (ทุก request ล้มเหลวหรือเซิร์ฟเวอร์รีสตาร์ทระหว่างวัด)")
        sys.exit(1)

    total_server = sum(stage_secs.values())
    print("เวลาประมวลผลฝั่งเซิร์ฟเวอร์เฉลี่ยต่อภาพของรอบนี้ (จาก /api/stats):")
    for stage, sec in stage_secs.items():
        print(f"  {stage:<16}{sec:.3f} วินาที")
    passed = "ผ่าน" if total_server < TARGET_SERVER_SEC else "ไม่ผ่าน"
    print(f"  {'รวม':<16}{total_server:.3f} วินาที — เป้า < {TARGET_SERVER_SEC:.0f} วินาที: {passed}")

    overall_request_avg = sum(sum(r["request_secs"]) / len(r["request_secs"]) for r in rows) / len(rows)
    print(f"\nเวลา request เฉลี่ยฝั่ง client (รวมอัปโหลด/เครือข่าย): {overall_request_avg:.3f} วินาที")
    print(f"ส่วนต่างที่เป็นอัปโหลด/เครือข่าย (โดยประมาณ): {overall_request_avg - total_server:.3f} วินาที")


if __name__ == "__main__":
    main()
