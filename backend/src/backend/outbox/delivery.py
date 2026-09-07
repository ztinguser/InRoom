from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.outbox.models import InboxEvent, OutboxEvent


async def deliver_one(db: AsyncSession) -> bool:
    event = await db.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.delivered_at.is_(None),
            OutboxEvent.available_at <= func.clock_timestamp(),
        )
        .order_by(OutboxEvent.available_at, OutboxEvent.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if event is None:
        return False

    event.attempts += 1

    try:
        async with db.begin_nested():
            await db.execute(
                insert(InboxEvent)
                .values(
                    event_id=event.id,
                    kind=event.kind,
                    payload=event.payload,
                )
                .on_conflict_do_nothing(
                    index_elements=[InboxEvent.event_id],
                )
            )
    except Exception as exc:
        event.error = type(exc).__name__
        delay = min(2 ** min(event.attempts, 6), 60)
        event.available_at = (
            await db.execute(select(func.clock_timestamp()))
        ).scalar_one() + timedelta(seconds=delay)
    else:
        event.delivered_at = (
            await db.execute(select(func.clock_timestamp()))
        ).scalar_one()
        event.error = None

    await db.flush()
    return True
