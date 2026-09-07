from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import AppError
from backend.jobs.models import Job
from backend.outbox.repository import add_event


async def _get_owned_job(
    db: AsyncSession,
    job_id: UUID,
    worker_id: str,
    token: int,
) -> tuple[Job, datetime]:
    """共同的检查"""
    job = await db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .with_for_update()
        # 如果当前数据库会话之前读过这条任务，也要用这次查询的最新字段刷新它，不能拿缓存中的旧领取信息判断！！
        .execution_options(populate_existing=True)
    )
    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()

    if (
        job is None
        or job.status != "running"
        or job.locked_by != worker_id
        or job.fencing_token != token
        or job.lease_until is None
        or job.lease_until <= now
    ):
        raise AppError(409, "JOB_LEASE_LOST", "任务处理权已失效")

    return job, now


async def complete_job(
    db: AsyncSession,
    job_id: UUID,
    worker_id: str,
    token: int,
    result: dict[str, Any],
) -> None:
    job, now = await _get_owned_job(db, job_id, worker_id, token)

    job.status = "completed"
    job.result = result
    job.error = None
    job.finished_at = now
    job.locked_by = None
    job.lease_until = None

    await add_event(
        db,
        "job.completed",
        {"job_id": str(job.id)},
    )


async def fail_job(
    db: AsyncSession,
    job_id: UUID,
    worker_id: str,
    token: int,
    error: str,
) -> None:
    job, now = await _get_owned_job(db, job_id, worker_id, token)

    job.error = error
    job.locked_by = None
    job.lease_until = None

    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = now
    else:
        delay = min(2**job.attempts, 60)
        job.status = "pending"
        job.available_at = now + timedelta(seconds=delay)
        job.finished_at = None

    await db.flush()


async def renew_job(
    db: AsyncSession,
    job_id: UUID,
    worker_id: str,
    token: int,
    lease_seconds: int = 30,
) -> None:
    """任务定期续租，当前时间 +30 秒"""
    job, now = await _get_owned_job(db, job_id, worker_id, token)

    job.lease_until = now + timedelta(seconds=lease_seconds)
    await db.flush()


async def cancel_job(
    db: AsyncSession,
    owner_id: UUID,
    job_id: UUID,
) -> Job:
    """取消：让任务失效，并阻止后续重试。取消由用户发起"""
    job = await db.scalar(
        select(Job)
        .where(
            Job.id == job_id,
            Job.owner_id == owner_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise AppError(404, "NOT_FOUND", "任务不存在")

    if job.status in {"completed", "failed", "cancelled"}:
        return job

    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()
    job.status = "cancelled"
    job.finished_at = now
    job.locked_by = None
    job.lease_until = None
    await db.flush()
    return job
