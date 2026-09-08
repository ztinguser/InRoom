from urllib.parse import unquote
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from backend.db.models import Preparation
from backend.preparations.models import ResumeAsset

# 超过 FileResponse 的单块大小，检查返回内容没有被截断。
CONTENT = b"%PDF-1.7\n" + b"download fixture\n" * 10000


@pytest.fixture
def uploaded_asset(upload_client):
    client, path, _ = upload_client
    response = client.post(path, files={"file": ("中文简历.pdf", CONTENT)})
    assert response.status_code == 201
    return response.json()["id"]


def test_owner_downloads_complete_file(upload_client, uploaded_asset):
    client, path, _ = upload_client
    client.headers.pop("Origin")
    client.headers.pop("X-CSRF-Token")

    response = client.get(f"{path}/{uploaded_asset}/download")

    assert response.status_code == 200
    assert response.content == CONTENT
    assert response.headers["content-type"] == "application/pdf"
    assert int(response.headers["content-length"]) == len(CONTENT)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert unquote(response.headers["content-disposition"]) == (
        "attachment; filename*=utf-8''中文简历.pdf"
    )


@pytest.mark.parametrize("case", ["anonymous", "other-owner", "missing-asset"])
def test_download_denies_unavailable_identity_or_asset(
    upload_client, uploaded_asset, case
):
    client, path, bob_cookie = upload_client
    if case == "anonymous":
        client.cookies.clear()
    elif case == "other-owner":
        client.cookies.set("inroom_session", bob_cookie)
    else:
        uploaded_asset = str(uuid4())

    response = client.get(f"{path}/{uploaded_asset}/download")

    assert response.status_code == (401 if case == "anonymous" else 404)
    assert response.json()["code"] == (
        "UNAUTHENTICATED" if case == "anonymous" else "NOT_FOUND"
    )


def test_download_rejects_wrong_preparation(
    upload_client, uploaded_asset, asset_database
):
    client, _, _ = upload_client
    engine, alice, _, _ = asset_database
    with Session(engine) as db, db.begin():
        other = Preparation(owner_id=alice)
        db.add(other)
        db.flush()
        other_id = other.id

    response = client.get(f"/preparations/{other_id}/assets/{uploaded_asset}/download")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_missing_disk_file_returns_service_error(
    upload_client, uploaded_asset, asset_database
):
    client, path, _ = upload_client
    with Session(asset_database[0]) as db:
        asset = db.get(ResumeAsset, UUID(uploaded_asset))
        client.app.state.object_store.delete(asset.object_key)

    response = client.get(f"{path}/{uploaded_asset}/download")

    assert response.status_code == 503
    assert response.json()["code"] == "FILE_UNAVAILABLE"
    with Session(asset_database[0]) as db:
        assert db.get(ResumeAsset, UUID(uploaded_asset)) is not None
