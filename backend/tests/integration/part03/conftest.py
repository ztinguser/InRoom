import asyncio
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db.models import User


def pytest_asyncio_loop_factories(config, item):
    # Psycopg 在 Windows 上也使用 Selector；仅作用于本目录。
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture
def isolated_url(database_url, migrate):
    schema = f"part03_{uuid4().hex}"
    admin = create_engine(database_url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = (
        make_url(database_url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    try:
        migrate(url)
        yield url
    finally:
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest_asyncio.fixture
async def sessions(isolated_url):
    engine = create_async_engine(isolated_url)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def owner(sessions):
    async with sessions.begin() as db:
        user = User(issuer="part03-test", subject=uuid4().hex)
        db.add(user)
        await db.flush()
        return user.id
