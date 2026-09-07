from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import AppError
from backend.jobs.models import Job


async def create_job(
    db: AsyncSession,
    owner_id: UUID,
    kind: str,
    payload: dict[str, Any],
    dedupe_key: str,
) -> Job:
    job = await db.scalar(
        insert(Job)
        .values(
            owner_id=owner_id,
            kind=kind,
            payload=payload,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(
            constraint="uq_jobs_owner_kind_dedupe",
        )
        .returning(Job)
    )
    if job is not None:
        return job

    result = await db.execute(
        select(Job).where(
            Job.owner_id == owner_id,
            Job.kind == kind,
            Job.dedupe_key == dedupe_key,
        )
    )
    existing = result.scalar_one()
    if existing.payload != payload:
        raise AppError(
            409,
            "JOB_CONFLICT",
            "相同任务标识不能使用不同参数",
        )
    return existing