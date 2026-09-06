from fastapi import FastAPI

from backend.auth.router import router as auth_router
from backend.core.config import Settings
from backend.core.http import configure_http
from backend.core.lifespan import lifespan
from backend.preparations.router import router as preparations_router


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="InRoom", lifespan=lifespan)
    app.state.settings = settings

    configure_http(app, settings)
    app.add_api_route("/health", health, methods=["GET"])
    app.include_router(auth_router)
    app.include_router(preparations_router)
    return app


app = create_app()
