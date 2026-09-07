import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.errors import AppError
from backend.db.models import Preparation, User
from backend.jobs.models import Job
from backend.jobs.repository import create_job
from backend.preparations.repository import create_preparation


def test_job_creation_and_rollback(database, database_url):
    async def run():
        engine = create_async_engine(database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        owner_id = uuid4()

        try:
            async with sessions.begin() as db:
                db.add(
                    User(
                        id=owner_id,
                        issuer="job-test",
                        subject=str(owner_id),
                    )
                )

            async def submit():
                async with sessions.begin() as db:
                    job = await create_job(
                        db,
                        owner_id,
                        "demo",
                        {"message": "hello"},
                        "same-request",
                    )
                    return job.id

            # 两个独立事务同时提交相同任务。
            first_id, second_id = await asyncio.gather(submit(), submit())
            assert first_id == second_id

            async with sessions() as db:
                count = await db.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.owner_id == owner_id)
                )
                assert count == 1

            # 相同标识不能悄悄换成其他参数。
            with pytest.raises(AppError) as exc:
                async with sessions.begin() as db:
                    await create_job(
                        db,
                        owner_id,
                        "demo",
                        {"message": "changed"},
                        "same-request",
                    )
            assert exc.value.code == "JOB_CONFLICT"

            # 业务数据和任务一起写入，随后故意制造失败。
            with pytest.raises(RuntimeError, match="injected failure"):
                async with sessions.begin() as db:
                    preparation = await create_preparation(db, owner_id)
                    job = await create_job(
                        db,
                        owner_id,
                        "parse_preparation",
                        {"preparation_id": str(preparation.id)},
                        f"parse:{preparation.id}",
                    )
                    preparation_id = preparation.id
                    rolled_back_job_id = job.id
                    raise RuntimeError("injected failure")

            async with sessions() as db:
                assert await db.get(Preparation, preparation_id) is None
                assert await db.get(Job, rolled_back_job_id) is None
                assert await db.get(Job, first_id) is not None
        finally:
            try:
                async with sessions.begin() as db:
                    await db.execute(delete(Job).where(Job.owner_id == owner_id))
                    await db.execute(
                        delete(Preparation).where(Preparation.owner_id == owner_id)
                    )
                    await db.execute(delete(User).where(User.id == owner_id))
            finally:
                await engine.dispose()

    asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)
