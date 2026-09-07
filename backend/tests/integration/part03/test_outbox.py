from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from backend.jobs.claiming import claim_job
from backend.jobs.models import Job
from backend.jobs.repository import create_job
from backend.jobs.results import complete_job
from backend.outbox.delivery import deliver_one
from backend.outbox.models import InboxEvent, OutboxEvent

pytestmark = pytest.mark.asyncio


async def test_atomic_completion_delivery_and_duplicate(sessions, owner):
    async with sessions.begin() as db:
        await create_job(db, owner, "demo", {}, "outbox")
        job = await claim_job(db, "a", ("demo",))
    # 数据库真实拒绝事件 INSERT：任务完成状态必须一起回滚。
    async with sessions.begin() as db:
        await db.execute(
            text(
                "ALTER TABLE outbox ADD CONSTRAINT injected_failure CHECK (kind <> 'job.completed')"
            )
        )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        async with sessions.begin() as db:
            await complete_job(db, job.id, "a", job.fencing_token, {"ok": True})
    async with sessions.begin() as db:
        assert (await db.get(Job, job.id)).status == "running"
        assert await db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        await db.execute(text("ALTER TABLE outbox DROP CONSTRAINT injected_failure"))
        await complete_job(db, job.id, "a", job.fencing_token, {"ok": True})

    # 投递事务在提交前崩溃：收件和已投递标记都不应残留。
    with pytest.raises(RuntimeError):
        async with sessions.begin() as db:
            assert await deliver_one(db)
            raise RuntimeError("before commit")
    async with sessions() as db:
        event = (await db.scalars(select(OutboxEvent))).one()
        event_id = event.id
        assert event.delivered_at is None
        assert await db.scalar(select(func.count()).select_from(InboxEvent)) == 0

    async with sessions.begin() as db:
        assert await deliver_one(db)
    async with sessions.begin() as db:
        received_at = (await db.get(InboxEvent, event_id)).received_at
        event = await db.get(OutboxEvent, event_id)
        assert event.delivered_at is not None
        event.delivered_at = None
    async with sessions.begin() as db:
        assert await deliver_one(db)
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(InboxEvent)) == 1
        assert (await db.get(InboxEvent, event_id)).received_at == received_at
        assert (await db.get(OutboxEvent, event_id)).attempts == 2


async def test_consumer_failure_is_retried(sessions, owner):
    async with sessions.begin() as db:
        await create_job(db, owner, "demo", {}, "consumer-failure")
        job = await claim_job(db, "a", ("demo",))
        await complete_job(db, job.id, "a", job.fencing_token, {})
        await db.execute(
            text(
                "ALTER TABLE inbox ADD CONSTRAINT injected_failure CHECK (kind <> 'job.completed')"
            )
        )
    async with sessions.begin() as db:
        assert await deliver_one(db)
    async with sessions.begin() as db:
        event = (await db.scalars(select(OutboxEvent))).one()
        assert event.delivered_at is None
        assert event.attempts == 1
        assert event.error == "IntegrityError"
        assert await deliver_one(db) is False
        await db.execute(text("ALTER TABLE inbox DROP CONSTRAINT injected_failure"))
        event.available_at = (
            await db.scalar(select(func.clock_timestamp()))
        ) - timedelta(seconds=1)
    async with sessions.begin() as db:
        assert await deliver_one(db)
    async with sessions() as db:
        event = (await db.scalars(select(OutboxEvent))).one()
        assert event.delivered_at is not None
        assert event.error is None
