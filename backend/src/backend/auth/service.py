from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import LoginSession, User


async def create_login(
    db: AsyncSession,
    issuer: str,
    subject: str,
    max_age: int,
    old_login_id: UUID | None = None,
) -> LoginSession:
    await db.execute(
        insert(User)
        .values(id=uuid4(), issuer=issuer, subject=subject)
        .on_conflict_do_nothing(index_elements=["issuer", "subject"])
    )
    result = await db.execute(
        select(User.id).where(User.issuer == issuer, User.subject == subject)
    )
    user_id = result.scalar_one()

    if old_login_id is not None:
        await db.execute(delete(LoginSession).where(LoginSession.id == old_login_id))

    login = LoginSession(
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(seconds=max_age),
    )
    db.add(login)
    await db.flush()
    return login


async def revoke_login(
    db: AsyncSession,
    login_id: UUID,
    user_id: UUID,
) -> None:
    await db.execute(
        delete(LoginSession).where(
            LoginSession.id == login_id,
            LoginSession.user_id == user_id,
        )
    )
