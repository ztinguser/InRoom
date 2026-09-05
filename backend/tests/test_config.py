from pathlib import Path

import pytest

from backend.config import Settings


def test_environment_overrides_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "APP_ENV=development\nLOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("LOG_LEVEL")

    settings = Settings()

    assert settings.app_env == "production"
    assert settings.log_level == "DEBUG"
