import pytest
from fastapi.testclient import TestClient

from agent import main
from backend.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UNDERCOVER_DB", str(tmp_path / "test.db"))
    with TestClient(app) as test_client:
        monkeypatch.setattr(main, "backend", lambda: TestClient(app))
        yield test_client
