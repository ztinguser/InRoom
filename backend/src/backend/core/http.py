import logging
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from backend.core.config import Settings
from backend.core.errors import AppError

logger = logging.getLogger(__name__)


async def request_context(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppError):
        status, code, message = exc.status, exc.code, exc.message
    elif isinstance(exc, RequestValidationError):
        status, code, message = 422, "INVALID_INPUT", "请求参数格式错误"
    elif isinstance(exc, HTTPException):
        status = exc.status_code
        code = "NOT_FOUND" if status == 404 else "HTTP_ERROR"
        message = str(exc.detail)
    elif isinstance(exc, (SQLAlchemyError, httpx.HTTPError)):
        status, code, message = 503, "SERVICE_UNAVAILABLE", "服务暂时不可用"
    else:
        status, code, message = 500, "INTERNAL_ERROR", "服务器内部错误"

    if status >= 500:
        logger.error(
            "Request failed, request_id=%s, type=%s",
            request.state.request_id,
            type(exc).__name__,
        )

    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": message,
            "request_id": request.state.request_id,
        },
        headers={
            "X-Request-ID": request.state.request_id,
            "Cache-Control": "no-store",
        },
    )


def configure_http(app: FastAPI, settings: Settings) -> None:
    app.middleware("http")(request_context)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="inroom_session",
        max_age=settings.login_max_age,
        same_site="lax",
        https_only=settings.app_origin.startswith("https://"),
    )
    for exception_type in (
        AppError,
        RequestValidationError,
        HTTPException,
        SQLAlchemyError,
        httpx.HTTPError,
        Exception,
    ):
        app.add_exception_handler(exception_type, handle_error)
