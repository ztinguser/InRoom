from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.models import LoginSession


def test_owner_isolation(users):
    alice, bob = users
    created = alice.post("/v1/preparations")
    assert created.status_code == 201
    path = f"/v1/preparations/{created.json()['id']}"
    assert alice.get(path).status_code == 200
    assert bob.get(path).status_code == 404
    assert (
        bob.post(f"{path}/cancel", json={"expected_state_version": 1}).status_code
        == 404
    )
    assert alice.get(path).json()["state_version"] == 1


def test_anonymous_and_invalid_cookie(server):
    with httpx.Client(base_url=server["origin"]) as client:
        assert client.get("/auth/me").status_code == 401
        assert client.post("/v1/preparations").status_code == 401
        client.cookies.set("inroom_session", "forged-cookie")
        assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize(
    "origin,csrf",
    [
        ("https://evil.example", "test-csrf"),
        ("null", "test-csrf"),
        (None, "test-csrf"),
        ("same", "wrong"),
        ("same", None),
    ],
)
def test_csrf_origin(users, server, origin, csrf):
    alice, _ = users
    alice.headers.pop("Origin")
    alice.headers.pop("X-CSRF-Token")
    headers = {}
    if origin is not None:
        headers["Origin"] = server["origin"] if origin == "same" else origin
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    response = alice.post("/v1/preparations", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_concurrent_version_conflict(users):
    alice, _ = users
    created = alice.post("/v1/preparations").json()
    path = f"/v1/preparations/{created['id']}"
    barrier = Barrier(2)

    def cancel():
        barrier.wait(timeout=10)
        return alice.post(f"{path}/cancel", json={"expected_state_version": 1})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: cancel(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["code"] == "VERSION_CONFLICT"
    assert alice.get(path).json()["state_version"] == 2


def test_expiry(users, database):
    alice, _ = users
    user_id = UUID(alice.get("/auth/me").json()["user_id"])
    with Session(database) as db, db.begin():
        db.execute(
            update(LoginSession)
            .where(LoginSession.user_id == user_id)
            .values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    assert alice.get("/auth/me").status_code == 401


def test_logout_revokes_cookie(users, database):
    alice, _ = users
    identity = alice.get("/auth/me").json()
    old_cookie = alice.cookies.get("inroom_session")
    assert alice.post("/auth/logout").status_code == 204
    alice.cookies.clear()
    alice.cookies.set("inroom_session", old_cookie)
    assert alice.get("/auth/me").status_code == 401
    with Session(database) as db:
        assert (
            db.scalar(
                select(LoginSession).where(
                    LoginSession.user_id == UUID(identity["user_id"]),
                )
            )
            is None
        )


def test_error_shape(users):
    alice, _ = users
    response = alice.get("/v1/preparations/not-a-uuid")
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "INVALID_INPUT"
    assert body["request_id"] == response.headers["x-request-id"]
