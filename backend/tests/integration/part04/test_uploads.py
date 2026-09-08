import asyncio
import json
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.api import create_app
from backend.core.config import Settings
from backend.db.models import LoginSession
from backend.preparations.models import ResumeAsset

PDF = b"%PDF-1.7\nheader-only upload fixture"


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


def test_upload_persists_record_and_private_file(upload_client, asset_database):
    client, path, _ = upload_client
    engine, alice, _, preparation = asset_database
    response = client.post(path, files={"file": ("resume.pdf", PDF, "application/pdf")})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "preparation_id", "filename", "size_bytes"}
    assert body["preparation_id"] == str(preparation)
    assert body["filename"] == "resume.pdf"
    assert body["size_bytes"] == len(PDF)
    with Session(engine) as db:
        asset = db.get(ResumeAsset, UUID(body["id"]))
        assert asset is not None
        assert asset.owner_id == alice
        store = client.app.state.object_store
        assert store.get(asset.object_key) == PDF
        assert client.get(f"/private/{asset.object_key}").status_code == 404


@pytest.mark.parametrize(
    ("case", "status"),
    [("anonymous", 401), ("other-owner", 404), ("csrf", 403), ("origin", 403)],
)
def test_upload_authorization(upload_client, asset_database, case, status):
    client, path, bob_cookie = upload_client
    if case == "anonymous":
        client.cookies.clear()
    elif case == "other-owner":
        client.cookies.set("inroom_session", bob_cookie)
    elif case == "csrf":
        client.headers.pop("X-CSRF-Token")
    else:
        client.headers["Origin"] = "https://other.example"

    response = client.post(path, files={"file": ("resume.pdf", PDF)})

    assert response.status_code == status
    assert list(client.app.state.object_store.root.iterdir()) == []
    with Session(asset_database[0]) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0


@pytest.mark.parametrize("content", [b"", b"this is not a PDF"])
def test_invalid_upload_leaves_no_file(upload_client, asset_database, content):
    client, path, _ = upload_client
    response = client.post(path, files={"file": ("resume.pdf", content)})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PDF"
    assert list(client.app.state.object_store.root.iterdir()) == []
    with Session(asset_database[0]) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0


def test_flush_failure_removes_uploaded_file(upload_client, asset_database):
    client, path, _ = upload_client
    engine = asset_database[0]
    with engine.begin() as db:
        db.execute(
            text("ALTER TABLE resume_assets ADD CONSTRAINT reject_upload CHECK (false)")
        )

    response = client.post(path, files={"file": ("resume.pdf", PDF)})

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert list(client.app.state.object_store.root.iterdir()) == []
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0


def test_commit_failure_keeps_file_for_reconciliation(upload_client, asset_database):
    client, path, _ = upload_client
    engine = asset_database[0]
    with engine.begin() as db:
        db.execute(
            text(
                "CREATE FUNCTION reject_upload_commit() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN "
                "RAISE EXCEPTION 'test commit failure' USING ERRCODE = '23514'; "
                "END $$"
            )
        )
        db.execute(
            text(
                "CREATE CONSTRAINT TRIGGER reject_upload_commit "
                "AFTER INSERT ON resume_assets DEFERRABLE INITIALLY DEFERRED "
                "FOR EACH ROW EXECUTE FUNCTION reject_upload_commit()"
            )
        )

    response = client.post(path, files={"file": ("resume.pdf", PDF)})

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    files = list(client.app.state.object_store.root.iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == PDF
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0
