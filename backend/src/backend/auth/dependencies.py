import secrets
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import func, select

from backend.core.errors import AppError
from backend.db.models import LoginSession, User
from backend.db.session import DB


async def current_user(request: Request, db: DB) -> User:
    login_id = request.session.get("login_id")
    if not login_id:
        raise AppError(401, "UNAUTHENTICATED", "请先登录")

    user = await db.scalar(
        select(User)
        .join(LoginSession, LoginSession.user_id == User.id)
        .where(
            LoginSession.id == UUID(login_id),
            LoginSession.expires_at > func.now(),
        )
    )
    if user is None:
        raise AppError(401, "UNAUTHENTICATED", "登录已过期")

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(request)
    return user


def check_csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    csrf = request.headers.get("x-csrf-token", "")
    expected = request.session.get("csrf", "")
    if (
        origin != request.app.state.settings.app_origin
        or not expected
        or not secrets.compare_digest(csrf.encode(), expected.encode())
    ):
        raise AppError(403, "FORBIDDEN", "请求来源或 CSRF 校验失败")


CurrentUser = Annotated[User, Depends(current_user)]
