import asyncio
import json
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.api import create_app
from backend.core.config import Settings
from backend.db.models import LoginSession


@pytest.fixture
def asset_database(database_url, migrate):
    schema = f"part04_{uuid4().hex}"
    admin = create_engine(database_url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = (
        make_url(database_url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    engine = create_engine(url)
    alice, bob, preparation = uuid4(), uuid4(), uuid4()
    try:
        migrate(url, "0006")
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO users (id, issuer, subject) VALUES (:id, 'part04', :name)"
                ),
                [{"id": alice, "name": "alice"}, {"id": bob, "name": "bob"}],
            )
            db.execute(
                text(
                    "INSERT INTO preparations (id, owner_id, status, state_version) "
                    "VALUES (:id, :owner, 'DRAFT', 3)"
                ),
                {"id": preparation, "owner": alice},
            )
        migrate(url, "0007")
        yield engine, alice, bob, preparation
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def upload_client(asset_database, tmp_path):
    engine, alice, bob, preparation = asset_database
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=engine.url.render_as_string(hide_password=False),
        app_origin="http://testserver",
        session_secret="upload-test-secret",
        private_storage_dir=tmp_path / "private",
    )
    cookies = []
    with Session(engine) as db, db.begin():
        for owner in [alice, bob]:
            login = LoginSession(
                user_id=owner,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            db.add(login)
            db.flush()
            payload = b64encode(
                json.dumps({"login_id": str(login.id), "csrf": "upload-csrf"}).encode()
            )
            cookies.append(TimestampSigner("upload-test-secret").sign(payload).decode())

    app = create_app(settings)
    with TestClient(
        app,
        raise_server_exceptions=False,
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        client.cookies.set("inroom_session", cookies[0])
        client.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": "upload-csrf"}
        )
        yield client, f"/preparations/{preparation}/assets", cookies[1]
