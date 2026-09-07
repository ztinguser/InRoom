import asyncio
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.config import Settings
from backend.jobs.claiming import claim_job
from backend.jobs.handlers import HANDLERS
from backend.jobs.runner import run_job

logger = logging.getLogger(__name__)


async def serve(settings: Settings, stop: asyncio.Event) -> None:
    worker_id = uuid4().hex
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000",
        },
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    kinds = tuple(HANDLERS)

    logger.info("Worker started, worker_id=%s", worker_id)

    try:
        while not stop.is_set():
            try:
                async with sessions.begin() as db:
                    job = await claim_job(db, worker_id, kinds)

                if job is not None:
                    logger.info(
                        "Job claimed, job_id=%s, attempt=%s",
                        job.id,
                        job.attempts,
                    )
                    await run_job(sessions, job, worker_id, HANDLERS[job.kind])
                    continue
            except Exception as exc:
                logger.warning(
                    "Worker cycle failed, error=%s",
                    type(exc).__name__,
                )

            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
    finally:
        await engine.dispose()
        logger.info("Worker stopped, worker_id=%s", worker_id)
