import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.errors import AppError
from backend.jobs.handlers import Handler
from backend.jobs.models import Job
from backend.jobs.results import complete_job, fail_job, renew_job

logger = logging.getLogger(__name__)


async def _heartbeat(
    sessions: async_sessionmaker[AsyncSession],
    job: Job,
    worker_id: str,
) -> None:
    while True:
        async with sessions.begin() as db:
            await renew_job(db, job.id, worker_id, job.fencing_token)
        await asyncio.sleep(10)


async def run_job(
    sessions: async_sessionmaker[AsyncSession],
    job: Job,
    worker_id: str,
    handler: Handler,
    timeout_seconds: float = 120,
) -> None:
    work = asyncio.create_task(handler(job.payload))
    heartbeat = asyncio.create_task(_heartbeat(sessions, job, worker_id))

    try:
        done, _ = await asyncio.wait(
            {work, heartbeat},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 心跳本应持续运行；提前结束说明续租出了问题。
        if heartbeat in done:
            await heartbeat

        error = None
        result = {}

        if work not in done:
            work.cancel()
            await asyncio.gather(work, return_exceptions=True)
            error = "任务执行超时"
        else:
            try:
                result = work.result()
            except Exception as exc:
                error = f"任务执行失败：{type(exc).__name__}"

        async with sessions.begin() as db:
            if error is None:
                await complete_job(
                    db,
                    job.id,
                    worker_id,
                    job.fencing_token,
                    result,
                )
            else:
                await fail_job(db, job.id, worker_id, job.fencing_token, error)

        if error is None:
            logger.info("Job completed, job_id=%s", job.id)
        else:
            logger.warning("Job attempt failed, job_id=%s, error=%s", job.id, error)

    except AppError as exc:
        if exc.code != "JOB_LEASE_LOST":
            raise
        logger.info("Job ownership lost, job_id=%s", job.id)
    finally:
        work.cancel()
        heartbeat.cancel()
        await asyncio.gather(work, heartbeat, return_exceptions=True)
