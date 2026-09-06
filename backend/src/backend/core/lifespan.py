import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.config import Settings
from backend.core.log import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.validate_production()
    settings.validate_identity()
    setup_logging(settings.log_level)

    engine = create_async_engine(settings.database_url)
    try:
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        oauth = OAuth()
        app.state.oidc = oauth.register(
            name="oidc",
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value(),
            server_metadata_url=(
                f"{settings.oidc_issuer}/.well-known/openid-configuration"
            ),
            client_kwargs={
                "scope": "openid",
                "code_challenge_method": "S256",
            },
        )
        logger.info("API started, environment=%s", settings.app_env)
        yield
    finally:
        await engine.dispose()
        logger.info("API stopped")
