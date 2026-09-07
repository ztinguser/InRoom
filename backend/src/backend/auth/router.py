import secrets
from uuid import UUID

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from joserfc.errors import JoseError

from backend.auth.dependencies import CurrentUser
from backend.auth.service import create_login, revoke_login
from backend.core.errors import AppError
from backend.db.session import DB

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    settings = request.app.state.settings
    return await request.app.state.oidc.authorize_redirect(
        request,
        f"{settings.app_origin}/auth/callback",
        prompt="select_account",
    )


@router.get("/callback")
async def callback(request: Request, db: DB):
    settings = request.app.state.settings
    try:
        token = await request.app.state.oidc.authorize_access_token(request)
    except (OAuthError, JoseError) as exc:
        raise AppError(401, "UNAUTHENTICATED", "登录验证失败，请重新登录") from exc

    identity = token.get("userinfo")
    if not identity or identity.get("iss") != settings.oidc_issuer:
        raise AppError(401, "UNAUTHENTICATED", "身份提供方不匹配")

    old_login_id = request.session.get("login_id")
    login_session = await create_login(
        db,
        issuer=identity["iss"],
        subject=identity["sub"],
        max_age=settings.login_max_age,
        old_login_id=UUID(old_login_id) if old_login_id else None,
    )
    request.session.clear()
    request.session.update(
        login_id=str(login_session.id),
        csrf=secrets.token_urlsafe(32),
    )
    return RedirectResponse("/auth/me", status_code=303)


@router.get("/me")
async def me(request: Request, user: CurrentUser):
    return {
        "user_id": str(user.id),
        "csrf_token": request.session["csrf"],
    }


@router.post("/logout", status_code=204)
async def logout(request: Request, db: DB, user: CurrentUser):
    await revoke_login(
        db,
        login_id=UUID(request.session["login_id"]),
        user_id=user.id,
    )
    request.session.clear()
