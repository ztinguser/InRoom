from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "kind",
            "dedupe_key",
            name="uq_jobs_owner_kind_dedupe",
        ),
        Index("ix_jobs_status_available_at", "status", "available_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )

    kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dedupe_key: Mapped[str]

    status: Mapped[str] = mapped_column(default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    locked_by: Mapped[str | None]
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    fencing_token: Mapped[int] = mapped_column(default=0)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
