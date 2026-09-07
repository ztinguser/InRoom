from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import AppError
from backend.db.session import DB
from backend.jobs.models import WorkerHeartbeat

router = APIRouter(prefix="/health", tags=["health"])


async def touch_worker(db: AsyncSession, worker_id: str) -> None:
    await db.execute(
        insert(WorkerHeartbeat)
        .values(
            worker_id=worker_id,
            last_seen=func.clock_timestamp(),
        )
        .on_conflict_do_update(
            index_elements=[WorkerHeartbeat.worker_id],
            set_={"last_seen": func.clock_timestamp()},
        )
    )


@router.get("/worker")
async def worker_health(db: DB) -> dict[str, str | int]:
    count = (
        await db.execute(
            select(func.count())
            .select_from(WorkerHeartbeat)
            .where(
                WorkerHeartbeat.last_seen
                > func.clock_timestamp() - timedelta(seconds=30)
            )
        )
    ).scalar_one()

    if count == 0:
        raise AppError(503, "WORKER_UNAVAILABLE", "暂无活跃的任务 Worker")

    return {"status": "ok", "workers": count}
