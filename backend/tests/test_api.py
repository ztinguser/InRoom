import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.api import create_app
from backend.core.config import Settings


def test_health() -> None:
    settings = Settings(session_secret="test-secret")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_rejects_invalid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "wrong")

    with pytest.raises(ValidationError) as exc_info:
        create_app()

    assert any(error["loc"] == ("app_env",) for error in exc_info.value.errors())
