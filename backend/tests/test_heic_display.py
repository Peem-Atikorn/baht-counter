"""HEIC/HEIF ต้องมีภาพ JPEG ที่พิกัดตรงกับผลนับ โดยไม่เปลี่ยนต้นฉบับ"""
import io
import json
import zipfile

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main, storage

client = TestClient(main.app)


def heif_bytes(orientation=1):
    # ลายสองสีช่วยตรวจว่าภาพแสดงผลไม่หมุนหรือกลับด้านซ้ำ
    image = Image.new("RGB", (120, 80), (30, 60, 180))
    image.paste((210, 40, 20), (0, 0, 60, 40))
    exif = Image.Exif()
    exif[274] = orientation
    buf = io.BytesIO()
    image.save(buf, format="HEIF", quality=95, exif=exif.tobytes())
    return buf.getvalue()


@pytest.mark.parametrize("media,extension", [("image/heic", ".heic"), ("image/heif", ".heif")])
@pytest.mark.parametrize("orientation", [1, 6])
def test_heif_display_is_jpeg_with_original_coordinates(media, extension, orientation):
    data = heif_bytes(orientation)
    response = client.post("/api/analyses", files={"file": (f"coins{extension}", data, media)})
    assert response.status_code == 201
    body = response.json()
    aid = body["analysis_id"]
    expected, _ = main.decode_image(data)
    height, width = expected.shape[:2]
    assert (width, height) == ((80, 120) if orientation == 6 else (120, 80))
    assert body["result"]["image_size"] == [width, height]

    display = client.get(f"/api/analyses/{aid}/images/original")
    assert display.status_code == 200
    assert display.headers["content-type"] == "image/jpeg"
    rendered = cv2.imdecode(np.frombuffer(display.content, np.uint8), cv2.IMREAD_COLOR)
    assert rendered.shape == expected.shape
    assert np.abs(rendered.astype(float) - expected).mean() < 8
    with Image.open(io.BytesIO(display.content)) as jpeg:
        assert jpeg.getexif().get(274, 1) == 1
    assert storage.load_image(aid, f"original{extension}") == data
    loaded, _ = main.load_original(main.get_or_404(aid))
    assert np.array_equal(loaded, expected)

    # ส่งผลที่แก้แล้วออกเป็นป้าย: zip ยังเก็บ HEIC เดิม ไม่ใช้ JPEG สำหรับแสดงผล
    edited = client.put(f"/api/analyses/{aid}/coins/0", json={"coin_type": "unknown"})
    assert edited.status_code == 200
    exported = client.get("/api/labels/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as zf:
        label = json.loads(zf.read(f"labels/{aid}.json"))
        assert label["image_size"] == [width, height]
        assert zf.read(f"raw/{aid}{extension}") == data


def test_legacy_heic_gets_display_jpeg_on_first_read(monkeypatch):
    save = storage.save_image
    def save_without_display(aid, filename, data):
        if filename != "display.jpg":
            save(aid, filename, data)
    with monkeypatch.context() as patch:
        patch.setattr(storage, "save_image", save_without_display)
        response = client.post("/api/analyses", files={"file": ("old.heic", heif_bytes(6), "image/heic")})
    assert response.status_code == 201
    aid = response.json()["analysis_id"]
    assert storage.load_image(aid, "display.jpg") is None
    result = client.get(f"/api/analyses/{aid}/images/original")
    assert result.status_code == 200
    assert result.headers["content-type"] == "image/jpeg"
    assert storage.load_image(aid, "display.jpg") == result.content
    # ครั้งต่อไปอ่านภาพที่เก็บไว้ ไม่ถอดรหัส HEIC ใหม่
    monkeypatch.setattr(main, "load_original", lambda _: pytest.fail("decoded cached image again"))
    assert client.get(f"/api/analyses/{aid}/images/original").content == result.content
