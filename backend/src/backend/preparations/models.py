from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKeyConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.models import Base


class ResumeAsset(Base):
    __tablename__ = "resume_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["preparation_id", "owner_id"],
            ["preparations.id", "preparations.owner_id"],
            name="fk_resume_assets_preparation_owner",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    preparation_id: Mapped[UUID] = mapped_column(index=True)
    owner_id: Mapped[UUID] = mapped_column(index=True)
    object_key: Mapped[str] = mapped_column(unique=True)
    filename: Mapped[str]
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
