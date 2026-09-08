import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    uploaded_keys: list[str] = []
    committing = False

    try:
        async with request.app.state.sessions.begin() as session:
            session.info["uploaded_keys"] = uploaded_keys
            yield session
            committing = True
    except BaseException:
        if not committing:
            for key in uploaded_keys:
                try:
                    await run_in_threadpool(request.app.state.object_store.delete, key)
                except OSError:
                    logger.warning("Upload cleanup failed, object_key=%s", key)
        raise


DB = Annotated[
    AsyncSession,
    Depends(get_db, scope="function"),
]
