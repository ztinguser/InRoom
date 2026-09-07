from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from joserfc.errors import BadSignatureError, ExpiredTokenError, InvalidClaimError

from backend.api import create_app
from backend.core.config import Settings


@pytest.mark.parametrize(
    "error", [BadSignatureError(), ExpiredTokenError("exp"), InvalidClaimError("nonce")]
)
def test_oidc_validation_errors_are_unauthenticated(error):
    settings = Settings(_env_file=None, app_env="test", session_secret="test-secret")
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.oidc.authorize_access_token = AsyncMock(side_effect=error)
        response = client.get("/auth/callback")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("environment", ["development", "production"])
def test_development_identity_cannot_be_enabled(environment):
    settings = Settings(
        _env_file=None,
        app_env=environment,
        dev_identity_enabled=True,
        session_secret="test-secret",
    )
    with pytest.raises(RuntimeError, match="不支持开发身份"):
        settings.validate_identity()


def test_production_secure_cookie():
    settings = Settings(
        _env_file=None,
        app_env="production",
        app_origin="https://inroom.example",
        oidc_issuer="https://identity.example",
        oidc_client_secret="test-secret",
        session_secret="test-secret",
        deepseek_api_key="test",
        deepseek_url="https://llm.example",
        dashscope_api_key="test",
        qwen_tts_voice="test",
    )
    app = create_app(settings)
    with TestClient(app, base_url=settings.app_origin) as client:

        async def begin(request, *args, **kwargs):
            from starlette.responses import RedirectResponse

            request.session["state"] = "test-state"
            return RedirectResponse(settings.oidc_issuer)

        app.state.oidc.authorize_redirect = begin
        response = client.get("/auth/login", follow_redirects=False)
    cookie = response.headers["set-cookie"].lower()
    assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_origin": "http://inroom.example"},
        {"oidc_issuer": "http://identity.example"},
        {"oidc_client_secret": ""},
    ],
)
def test_production_identity_configuration(overrides):
    values = dict(
        app_env="production",
        app_origin="https://inroom.example",
        oidc_issuer="https://identity.example",
        oidc_client_secret="test-secret",
        session_secret="test-secret",
    )
    values.update(overrides)
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, **values).validate_identity()
