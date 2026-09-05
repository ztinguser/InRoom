import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_rejects_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "wrong")

    with pytest.raises(ValidationError) as exc_info, TestClient(app):
        pass

    assert any(error["loc"] == ("app_env",) for error in exc_info.value.errors())
