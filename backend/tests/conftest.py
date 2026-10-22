import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """ทุกเทสต์ใช้ SQLite + storage/ ของตัวเอง ไม่ปนกับเทสต์อื่นหรือ storage/ จริง"""
    monkeypatch.setenv("BAHT_DATA_DIR", str(tmp_path / "storage"))


@pytest.fixture(autouse=True)
def default_to_mock_pipeline(monkeypatch):
    """เทสต์ของ backend/app (API/pipeline) คาดเดาผลตายตัวจาก mock_*() ของทุกโมดูล

    ค่าเริ่มต้นของระบบจริง (docker compose, Render) เปลี่ยนเป็น COIN_USE_MOCK=0 (ของจริงทั้งหมด) แล้ว
    แต่เทสต์เหล่านี้ยังต้องพึ่งผลตายตัวของ mock ทับค่าเริ่มต้นไว้เป็น "1" ที่นี่ เทสต์ที่ตั้ง COIN_USE_MOCK
    เอง (monkeypatch.setenv ในตัวเทสต์) ยังชนะอยู่ เพราะเทสต์รันหลัง fixture นี้เสมอ
    """
    monkeypatch.setenv("COIN_USE_MOCK", "1")
