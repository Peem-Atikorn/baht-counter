import cv2
import numpy as np
from fastapi.testclient import TestClient

from app import main
from app.main import app

client = TestClient(app)


def png_bytes(w=800, h=600) -> bytes:
    _, buf = cv2.imencode(".png", np.full((h, w, 3), 255, np.uint8))
    return buf.tobytes()


def upload(data: bytes, content_type="image/png"):
    return client.post("/api/analyses", files={"file": ("coins.png", data, content_type)})


def test_coin_types():
    r = client.get("/api/coin-types")
    assert r.status_code == 200
    assert [t["code"] for t in r.json()] == ["THB_0_25", "THB_0_50", "THB_1", "THB_2", "THB_5", "THB_10"]


def test_create_and_get_analysis():
    r = upload(png_bytes())
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["image_size"] == [800, 600]
    assert len(body["result"]["coins"]) == 6

    r2 = client.get(f"/api/analyses/{body['analysis_id']}")
    assert r2.status_code == 200
    assert r2.json() == body


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


def test_unknown_analysis_404():
    assert client.get("/api/analyses/does-not-exist").status_code == 404


def test_rejects_too_many_pixels(monkeypatch):
    monkeypatch.setattr(main, "MAX_PIXELS", 800 * 600 - 1)
    r = upload(png_bytes(800, 600))
    assert r.status_code == 413
    assert "ความละเอียดสูงเกินไป" in r.json()["detail"]


def test_keeps_only_recent_analyses(monkeypatch):
    monkeypatch.setattr(main, "MAX_ANALYSES", 2)
    ids = [upload(png_bytes(80, 60)).json()["analysis_id"] for _ in range(3)]
    assert client.get(f"/api/analyses/{ids[0]}").status_code == 404
    assert all(client.get(f"/api/analyses/{i}").status_code == 200 for i in ids[1:])
