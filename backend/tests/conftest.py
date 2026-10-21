import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """ทุกเทสต์ใช้ SQLite + storage/ ของตัวเอง ไม่ปนกับเทสต์อื่นหรือ storage/ จริง"""
    monkeypatch.setenv("BAHT_DATA_DIR", str(tmp_path / "storage"))
