import asyncio
import sys
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.core.config import Settings
from backend.db.models import User
from backend.jobs.models import Job
from backend.jobs.repository import create_job


async def main() -> None:
    settings = Settings()
    if settings.app_env != "development":
        raise RuntimeError("演示命令只用于开发环境")

    engine = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions.begin() as db:
            owner_id = await db.scalar(select(User.id).limit(1))
            if owner_id is None:
                raise RuntimeError("开发库没有用户，请先登录一次")

            job = await create_job(
                db,
                owner_id,
                "demo",
                {"seconds": 2, "message": "后台任务完成了"},
                uuid4().hex,
            )
            job_id = job.id

        print(f"任务已提交：{job_id}")

        for _ in range(30):
            async with sessions() as db:
                current = await db.get(Job, job_id)
                if current is None:
                    raise RuntimeError("任务记录不存在")

                print(f"{current.status}，已尝试 {current.attempts} 次")
                if current.status in {"completed", "failed", "cancelled"}:
                    print(f"结果：{current.result}")
                    print(f"错误：{current.error}")
                    return

            await asyncio.sleep(1)

        print("等待结束，任务仍在数据库中，请检查 Worker")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(
        main(),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )
