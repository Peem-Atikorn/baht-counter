import io
import json
import zipfile

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def png_bytes(w=800, h=600) -> bytes:
    _, buf = cv2.imencode(".png", np.full((h, w, 3), 255, np.uint8))
    return buf.tobytes()


def upload(data: bytes, content_type="image/png", filename="coins.png"):
    return client.post("/api/analyses", files={"file": (filename, data, content_type)})


def create_analysis(filename="coins.png") -> dict:
    return upload(png_bytes(), filename=filename).json()


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_coin_types():
    r = client.get("/api/coin-types")
    assert r.status_code == 200
    assert [t["code"] for t in r.json()] == ["THB_0_25", "THB_0_50", "THB_1", "THB_2", "THB_5", "THB_10"]


def test_create_and_get_analysis():
    r = upload(png_bytes())
    assert r.status_code == 201  # ส่วนที่ 4 เปลี่ยนจาก 200 เป็น 201 (resource ถูกสร้างขึ้นจริง)
    body = r.json()
    assert body["result"]["image_size"] == [800, 600]
    assert len(body["result"]["coins"]) == 6

    r2 = client.get(f"/api/analyses/{body['analysis_id']}")
    assert r2.status_code == 200
    assert r2.json() == body


def test_create_analysis_persists_across_fresh_client():
    """เก็บใน SQLite + storage/ จริง ไม่ใช่ตัวแปรในหน่วยความจำ — ไคลเอนต์ใหม่ (จำลองรีสตาร์ท) ต้องยังอ่านได้"""
    body = create_analysis()
    fresh_client = TestClient(app)
    r = fresh_client.get(f"/api/analyses/{body['analysis_id']}")
    assert r.status_code == 200
    assert r.json() == body


def test_images_are_served():
    body = upload(png_bytes()).json()
    aid = body["analysis_id"]
    assert client.get(f"/api/analyses/{aid}/images/original").headers["content-type"] == "image/png"
    gray_url = body["result"]["debug_images"]["gray"]
    assert client.get(gray_url).status_code == 200
    assert client.get(f"/api/analyses/{aid}/images/nope").status_code == 404


def test_rejects_wrong_type():
    r = upload(b"hello", "text/plain")
    assert r.status_code == 415


def test_rejects_corrupt_image():
    r = upload(b"not really a png")
    assert r.status_code == 400
    assert "อ่านไฟล์ภาพไม่ได้" in r.json()["detail"]


def test_rejects_too_large():
    r = upload(b"0" * (15 * 1024 * 1024 + 1))
    assert r.status_code == 413


def test_rejects_too_many_pixels(monkeypatch):
    monkeypatch.setattr(main, "MAX_PIXELS", 800 * 600 - 1)
    r = upload(png_bytes(800, 600))
    assert r.status_code == 413
    assert "ความละเอียดสูงเกินไป" in r.json()["detail"]


def test_unknown_analysis_404():
    assert client.get("/api/analyses/does-not-exist").status_code == 404


def test_update_coin_sets_user_edited_and_recomputes_scale():
    body = create_analysis()
    aid = body["analysis_id"]
    coin_id = body["result"]["coins"][5]["coin_id"]

    r = client.put(f"/api/analyses/{aid}/coins/{coin_id}", json={"coin_type": "THB_10"})
    assert r.status_code == 200
    result = r.json()["result"]
    edited = next(c for c in result["coins"] if c["coin_id"] == coin_id)
    assert edited["coin_type"] == "THB_10"
    assert edited["source"] == "user_edited"
    assert edited["status"] == "ok"
    assert result["status"] == "ok"
    assert result["scale_source"] == "user_anchor"
    assert result["total_baht"] is not None


def test_update_coin_keeps_previously_edited_coin():
    """แก้เหรียญที่สองแล้วเหรียญแรกที่ผู้ใช้ยืนยันไว้ก่อนต้องยังเป็นชนิดเดิมถาวร (รีวิว PR #19 ข้อ 3)"""
    body = create_analysis()
    aid = body["analysis_id"]
    coins = body["result"]["coins"]

    first = client.put(f"/api/analyses/{aid}/coins/{coins[0]['coin_id']}", json={"coin_type": "THB_10"}).json()
    assert first["result"]["coins"][0]["coin_type"] == "THB_10"

    second = client.put(f"/api/analyses/{aid}/coins/{coins[1]['coin_id']}", json={"coin_type": "THB_5"}).json()
    coin0 = next(c for c in second["result"]["coins"] if c["coin_id"] == coins[0]["coin_id"])
    assert coin0["coin_type"] == "THB_10"
    assert coin0["source"] == "user_edited"
    coin1 = next(c for c in second["result"]["coins"] if c["coin_id"] == coins[1]["coin_id"])
    assert coin1["coin_type"] == "THB_5"

    # ยังอยู่ถาวรหลัง GET ใหม่ (ไม่ใช่แค่ใน response ของ PUT)
    reread = client.get(f"/api/analyses/{aid}").json()
    coin0_again = next(c for c in reread["result"]["coins"] if c["coin_id"] == coins[0]["coin_id"])
    assert coin0_again["coin_type"] == "THB_10"


def test_update_coin_to_unknown_does_not_500():
    body = create_analysis()
    aid = body["analysis_id"]
    coin_id = body["result"]["coins"][2]["coin_id"]

    r = client.put(f"/api/analyses/{aid}/coins/{coin_id}", json={"coin_type": "unknown"})
    assert r.status_code == 200
    result = r.json()["result"]
    edited = next(c for c in result["coins"] if c["coin_id"] == coin_id)
    assert edited["coin_type"] == "unknown"
    assert edited["value_baht"] is None
    assert edited["source"] == "user_edited"
    assert edited["status"] == "ok"
    assert result["total_baht"] is None  # มีเหรียญที่ระบุมูลค่าไม่ได้ (unknown) ห้ามรวมเป็นตัวเลข


def test_update_coin_to_unknown_after_anchor_still_200():
    body = create_analysis()
    aid = body["analysis_id"]
    coins = body["result"]["coins"]
    client.put(f"/api/analyses/{aid}/coins/{coins[0]['coin_id']}", json={"coin_type": "THB_10"})

    r = client.put(f"/api/analyses/{aid}/coins/{coins[1]['coin_id']}", json={"coin_type": "unknown"})
    assert r.status_code == 200


def test_update_unknown_coin_404():
    body = create_analysis()
    r = client.put(f"/api/analyses/{body['analysis_id']}/coins/999", json={"coin_type": "THB_10"})
    assert r.status_code == 404


def test_update_coin_unknown_analysis_404():
    r = client.put("/api/analyses/does-not-exist/coins/0", json={"coin_type": "THB_10"})
    assert r.status_code == 404


def test_add_coin_needs_confirmation_until_typed():
    body = create_analysis()
    aid = body["analysis_id"]
    before = len(body["result"]["coins"])

    r = client.post(f"/api/analyses/{aid}/coins", json={"xy": [100.0, 50.0]})
    assert r.status_code == 201
    result = r.json()["result"]
    assert len(result["coins"]) == before + 1
    added = result["coins"][-1]
    assert added["source"] == "user_added"
    assert added["status"] == "needs_confirmation"
    assert added["center_xy"] == [100.0, 50.0]
    assert result["status"] == "needs_confirmation"
    assert result["total_baht"] is None  # มีเหรียญที่ยังระบุชนิดไม่ได้ ห้ามรวมเป็นตัวเลข


def test_add_coin_unknown_analysis_404():
    r = client.post("/api/analyses/does-not-exist/coins", json={"xy": [1.0, 1.0]})
    assert r.status_code == 404


def test_added_coin_with_fake_radius_is_not_used_as_anchor():
    """เหรียญที่เพิ่มเองมีรัศมีสมมติ แก้ชนิดให้แล้วต้องไม่กระทบสเกล/ชนิดของเหรียญอื่น (รีวิว PR #19 ข้อ 6)"""
    body = create_analysis()
    aid = body["analysis_id"]
    original_coin_id = body["result"]["coins"][0]["coin_id"]

    resolved = client.put(
        f"/api/analyses/{aid}/coins/{original_coin_id}", json={"coin_type": "THB_10"},
    ).json()["result"]
    before_scale = resolved["scale_mm_per_px"]
    before_types = {c["coin_id"]: c["coin_type"] for c in resolved["coins"]}
    assert before_scale is not None

    added = client.post(f"/api/analyses/{aid}/coins", json={"xy": [400.0, 300.0]}).json()["result"]
    new_coin_id = added["coins"][-1]["coin_id"]

    r = client.put(f"/api/analyses/{aid}/coins/{new_coin_id}", json={"coin_type": "THB_5"})
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["scale_mm_per_px"] == before_scale
    for coin_id, coin_type in before_types.items():
        assert next(c for c in result["coins"] if c["coin_id"] == coin_id)["coin_type"] == coin_type
    added_coin = next(c for c in result["coins"] if c["coin_id"] == new_coin_id)
    assert added_coin["coin_type"] == "THB_5"
    assert added_coin["source"] == "user_edited"


def test_delete_coin_recomputes_total():
    body = create_analysis()
    aid = body["analysis_id"]
    coins = body["result"]["coins"]

    r = client.delete(f"/api/analyses/{aid}/coins/{coins[-1]['coin_id']}")  # เหรียญ needs_confirmation ของ mock
    assert r.status_code == 200
    result = r.json()["result"]
    assert len(result["coins"]) == len(coins) - 1
    assert result["status"] == "ok"
    assert result["total_baht"] is not None


def test_delete_last_coin_leaves_failed_not_zero():
    body = create_analysis()
    aid = body["analysis_id"]
    for c in body["result"]["coins"]:
        r = client.delete(f"/api/analyses/{aid}/coins/{c['coin_id']}")
        assert r.status_code == 200
    result = r.json()["result"]
    assert result["coins"] == []
    assert result["status"] == "failed"
    assert result["total_baht"] is None  # ไม่มีเหรียญ ห้ามแสดงเป็น 0


def test_delete_unknown_coin_404():
    body = create_analysis()
    r = client.delete(f"/api/analyses/{body['analysis_id']}/coins/999")
    assert r.status_code == 404


def test_history_lists_newest_first():
    first = create_analysis()
    second = create_analysis()
    r = client.get("/api/history")
    assert r.status_code == 200
    page = r.json()
    ids = [item["analysis_id"] for item in page["items"]]
    assert ids.index(second["analysis_id"]) < ids.index(first["analysis_id"])
    assert page["total"] >= 2


def test_history_rejects_invalid_limit():
    assert client.get("/api/history", params={"limit": 0}).status_code == 422
    assert client.get("/api/history", params={"offset": -1}).status_code == 422


def test_export_json_and_csv():
    body = create_analysis()
    aid = body["analysis_id"]

    r_json = client.get(f"/api/analyses/{aid}/export", params={"format": "json"})
    assert r_json.status_code == 200
    assert r_json.json()["analysis_id"] == aid

    r_csv = client.get(f"/api/analyses/{aid}/export", params={"format": "csv"})
    assert r_csv.status_code == 200
    assert r_csv.headers["content-type"].startswith("text/csv")
    assert r_csv.text.splitlines()[0] == "coin_id,coin_type,value_baht,color_group,source,status,center_x,center_y,radius_px"


def test_export_unknown_analysis_404():
    assert client.get("/api/analyses/does-not-exist/export").status_code == 404


def test_labels_export_empty_is_404():
    r = client.get("/api/labels/export")
    assert r.status_code == 404


def test_labels_export_has_unique_names_and_raw_images():
    """สองภาพชื่อไฟล์เดิมซ้ำกัน (เช่น capture.jpg จากกล้องในหน้าเว็บ) ต้องไม่ทับกันใน zip (รีวิว PR #19 ข้อ 5)"""
    first = create_analysis(filename="capture.jpg")
    second = create_analysis(filename="capture.jpg")
    for body in (first, second):
        coin_id = body["result"]["coins"][0]["coin_id"]
        client.put(f"/api/analyses/{body['analysis_id']}/coins/{coin_id}", json={"coin_type": "THB_5"})

    r = client.get("/api/labels/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert len(names) == len(set(names))  # ไม่มีชื่อซ้ำ
        assert f"labels/{first['analysis_id']}.json" in names
        assert f"labels/{second['analysis_id']}.json" in names
        label = json.loads(zf.read(f"labels/{first['analysis_id']}.json"))
        assert label["source_filename"] == "capture.jpg"
        assert label["image"] != "capture.jpg"  # ชื่อไฟล์ในซิปใช้ analysis_id ไม่ใช่ชื่อเดิม
        assert f"raw/{label['image']}" in names


def test_stats_reports_edit_count():
    body = create_analysis()
    aid = body["analysis_id"]
    coin_id = body["result"]["coins"][0]["coin_id"]
    client.put(f"/api/analyses/{aid}/coins/{coin_id}", json={"coin_type": "THB_5"})

    r = client.get("/api/stats")
    assert r.status_code == 200
    stats = r.json()
    assert stats["analyses_count"] >= 1
    assert stats["total_edits"] >= 1
    assert set(stats["avg_timings_sec"]) >= {"preprocess", "detection", "classification"}
