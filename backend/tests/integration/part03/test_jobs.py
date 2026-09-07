import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from backend.core.errors import AppError
from backend.jobs.claiming import claim_job
from backend.jobs.models import Job
from backend.jobs.repository import create_job
from backend.jobs.results import cancel_job, complete_job, fail_job, renew_job
from backend.jobs.runner import run_job
from backend.outbox.models import OutboxEvent

pytestmark = pytest.mark.asyncio


async def test_competing_claim_and_stale_owner(sessions, owner):
    async with sessions.begin() as db:
        job = await create_job(db, owner, "demo", {}, "claim")
    async with sessions.begin() as first:
        claimed = await claim_job(first, "a", ("demo",))
        assert claimed.id == job.id
        token = claimed.fencing_token
        async with sessions.begin() as second:
            assert await asyncio.wait_for(claim_job(second, "b", ("demo",)), 2) is None
    async with sessions.begin() as db:
        assert await claim_job(db, "b", ("demo",)) is None
        await db.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with sessions.begin() as db:
        replacement = await claim_job(db, "b", ("demo",))
        assert replacement.fencing_token == token + 1
    for action, extra in (
        (complete_job, ({"stale": True},)),
        (fail_job, ("old error",)),
        (renew_job, ()),
    ):
        with pytest.raises(AppError) as error:
            async with sessions.begin() as db:
                await action(db, job.id, "a", token, *extra)
        assert error.value.code == "JOB_LEASE_LOST"
    async with sessions.begin() as db:
        await complete_job(db, job.id, "b", replacement.fencing_token, {"fresh": True})
    async with sessions() as db:
        saved = await db.get(Job, job.id)
        assert saved.result == {"fresh": True}
        assert await db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


async def test_retry_backoff_and_limit(sessions, owner):
    async with sessions.begin() as db:
        job = await create_job(db, owner, "demo", {}, "retry")
    for attempt in range(1, 4):
        async with sessions.begin() as db:
            claimed = await claim_job(db, "a", ("demo",))
            assert claimed.attempts == attempt
            before = await db.scalar(select(func.clock_timestamp()))
            await fail_job(db, job.id, "a", claimed.fencing_token, "injected")
        async with sessions.begin() as db:
            saved = await db.get(Job, job.id)
            assert saved.status == ("pending" if attempt < 3 else "failed")
            assert await claim_job(db, "b", ("demo",)) is None
            if attempt < 3:
                assert saved.available_at >= before + timedelta(seconds=2**attempt)
                saved.available_at = before - timedelta(seconds=1)
            else:
                assert saved.finished_at is not None
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(OutboxEvent)) == 0


@pytest.mark.parametrize("running", [False, True])
async def test_cancel_cannot_revive(sessions, owner, running):
    async with sessions.begin() as db:
        job = await create_job(db, owner, "demo", {}, "cancel")
        if running:
            job = await claim_job(db, "a", ("demo",))
        token = job.fencing_token
    async with sessions.begin() as db:
        await cancel_job(db, owner, job.id)
        await cancel_job(db, owner, job.id)
    for action, extra in (
        (complete_job, ({},)),
        (fail_job, ("late",)),
        (renew_job, ()),
    ):
        with pytest.raises(AppError) as error:
            async with sessions.begin() as db:
                await action(db, job.id, "a", token, *extra)
        assert error.value.code == "JOB_LEASE_LOST"
    async with sessions.begin() as db:
        assert await claim_job(db, "b", ("demo",)) is None
        assert (await db.get(Job, job.id)).status == "cancelled"


async def test_runner_timeout_cleans_up(sessions, owner):
    stopped = asyncio.Event()

    async def slow(payload):
        try:
            await asyncio.sleep(60)
            return {}
        finally:
            stopped.set()

    async with sessions.begin() as db:
        await create_job(db, owner, "demo", {}, "timeout")
        job = await claim_job(db, "a", ("demo",))
    await asyncio.wait_for(run_job(sessions, job, "a", slow, timeout_seconds=0.2), 5)
    assert stopped.is_set()
    async with sessions() as db:
        saved = await db.get(Job, job.id)
        assert saved.status == "pending"
        assert saved.error == "任务执行超时"
        assert saved.locked_by is None
