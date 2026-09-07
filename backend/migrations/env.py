import asyncio
import sys

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from backend.core.config import Settings
from backend.db.models import Base
from backend.jobs.models import Job  # noqa: F401
from backend.outbox.models import OutboxEvent  # noqa: F401

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(
        Settings().database_url,
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    # Psycopg 的异步连接在 Windows 上需要 Selector 事件循环。
    asyncio.run(
        run_online(),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )
