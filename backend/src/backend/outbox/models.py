from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_delivered_available", "delivered_at", "available_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)

    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    error: Mapped[str | None]


class InboxEvent(Base):
    __tablename__ = "inbox"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
