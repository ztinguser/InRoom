from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.outbox.models import OutboxEvent


async def add_event(
    db: AsyncSession,
    kind: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(kind=kind, payload=payload)
    db.add(event)
    await db.flush()
    return event
