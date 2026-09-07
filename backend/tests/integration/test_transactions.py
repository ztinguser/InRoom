import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import create_app
from backend.core.config import Settings
from backend.db.models import Preparation, User
from backend.db.session import DB
from backend.preparations.repository import create_preparation


def test_request_rolls_back_all_writes(database, database_url):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        session_secret="transaction-test",
    )
    app = create_app(settings)
    user_id = uuid4()
    written = []

    @app.post("/test/fail")
    async def fail(db: DB):
        db.add(User(id=user_id, issuer="rollback-test", subject=str(user_id)))
        await db.flush()
        preparation = await create_preparation(db, user_id)
        written.append(preparation.id)
        raise RuntimeError("injected failure after two INSERTs")

    with TestClient(
        app,
        raise_server_exceptions=False,
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        response = client.post("/test/fail")
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"

    async def verify():
        engine = create_async_engine(database_url)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                assert await db.get(User, user_id) is None
                assert await db.get(Preparation, written[0]) is None
        finally:
            await engine.dispose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)


def test_commit_failure_does_not_send_success(database, database_url):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        session_secret="transaction-test",
    )
    app = create_app(settings)

    @app.post("/test/commit", status_code=201)
    async def fail_at_commit(db: DB):
        # 不 flush：外键错误在依赖退出、提交事务时发生。
        db.add(Preparation(owner_id=uuid4()))
        return {"saved": True}

    with TestClient(
        app,
        raise_server_exceptions=False,
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        response = client.post("/test/commit")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
