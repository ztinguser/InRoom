from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import AppError
from backend.db.models import Preparation


async def create_preparation(
    db: AsyncSession,
    owner_id: UUID,
) -> Preparation:
    preparation = Preparation(owner_id=owner_id)
    db.add(preparation)
    await db.flush()
    return preparation


async def get_preparation(
    db: AsyncSession,
    owner_id: UUID,
    preparation_id: UUID,
) -> Preparation:
    preparation = await db.scalar(
        select(Preparation).where(
            Preparation.id == preparation_id,
            Preparation.owner_id == owner_id,
        )
    )
    if preparation is None:
        raise AppError(404, "NOT_FOUND", "准备工作区不存在")
    return preparation


async def cancel_preparation(
    db: AsyncSession,
    owner_id: UUID,
    preparation_id: UUID,
    expected_version: int,
) -> Preparation:
    preparation = await db.scalar(
        update(Preparation)
        .where(
            Preparation.id == preparation_id,
            Preparation.owner_id == owner_id,
            Preparation.state_version == expected_version,
        )
        .values(
            status="CANCELLED",
            state_version=Preparation.state_version + 1,
        )
        .returning(Preparation)
    )

    if preparation is None:
        await get_preparation(db, owner_id, preparation_id)
        raise AppError(
            409,
            "VERSION_CONFLICT",
            "数据已更新，请刷新后重试",
        )

    return preparation
