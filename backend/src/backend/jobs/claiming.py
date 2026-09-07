from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.jobs.models import Job


async def claim_job(
    db: AsyncSession,
    worker_id: str,
    kinds: tuple[str, ...],
    lease_seconds: int = 30,
) -> Job | None:
    job = await db.scalar(
        select(Job)
        .where(
            Job.kind.in_(kinds),
            or_(
                and_(
                    Job.status == "pending", Job.available_at <= func.clock_timestamp()
                ),
                and_(
                    Job.status == "running", Job.lease_until <= func.clock_timestamp()
                ),
            ),
        )
        .order_by(Job.available_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    now = (await db.execute(select(func.clock_timestamp()))).scalar_one()

    # 最后一次执行也可能崩溃，租约到期后需要明确标记失败。
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.error = "任务执行次数已耗尽"
        job.locked_by = None
        job.lease_until = None
        job.finished_at = now
        await db.flush()
        return None

    job.status = "running"
    job.locked_by = worker_id
    job.lease_until = now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    job.fencing_token += 1
    await db.flush()
    return job
