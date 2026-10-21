"""เทสต์ main.mount_frontend แยกเป็น FastAPI app เล็กของตัวเอง ไม่ใช้ app จริง (ไม่มี frontend_dist ตอน pytest)
รีวิว PR #19 ข้อ 2: path traversal ตอนเสิร์ฟหน้าเว็บที่ build แล้ว
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import mount_frontend


@pytest.fixture
def frontend_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("console.log('ok')")
    (dist / "index.html").write_text("<html>index</html>")
    (tmp_path / "secret.txt").write_text("TOP SECRET")  # อยู่นอก dist โดยตั้งใจ

    app = FastAPI()
    mount_frontend(app, dist)
    return TestClient(app)


def test_root_serves_index(frontend_client):
    r = frontend_client.get("/")
    assert r.status_code == 200
    assert "index" in r.text


def test_client_route_falls_back_to_index(frontend_client):
    r = frontend_client.get("/result/abc")
    assert r.status_code == 200
    assert "index" in r.text


def test_asset_file_served(frontend_client):
    r = frontend_client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_api_path_still_404s(frontend_client):
    assert frontend_client.get("/api/nope").status_code == 404


def test_path_traversal_percent_encoded_dot_dot_blocked(frontend_client):
    r = frontend_client.get("/%2e%2e/secret.txt")
    assert "TOP SECRET" not in r.text


def test_path_traversal_percent_encoded_slash_blocked(frontend_client):
    r = frontend_client.get("/..%2fsecret.txt")
    assert "TOP SECRET" not in r.text


def test_path_traversal_literal_dot_dot_blocked(frontend_client):
    r = frontend_client.get("/../secret.txt")
    assert "TOP SECRET" not in r.text
