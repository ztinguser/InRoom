import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.config import Settings
from backend.outbox.delivery import deliver_one

logger = logging.getLogger(__name__)


async def serve(settings: Settings, stop: asyncio.Event) -> None:
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000",
        },
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    logger.info("Outbox started")

    try:
        while not stop.is_set():
            try:
                async with sessions.begin() as db:
                    handled = await deliver_one(db)

                if handled:
                    continue
            except Exception as exc:
                logger.warning(
                    "Outbox cycle failed, error=%s",
                    type(exc).__name__,
                )

            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
    finally:
        await engine.dispose()
        logger.info("Outbox stopped")
