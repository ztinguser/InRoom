from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.db.models import LoginSession, Preparation, User


class LoginForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values["action"]
        if tag == "input" and values.get("type") == "hidden" and values.get("name"):
            self.fields[values["name"]] = values.get("value", "")


def authorize(client, keycloak, username):
    start = client.get("/auth/login")
    assert start.status_code in {302, 307}
    cookie = start.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    authorization = start.headers["location"]
    query = parse_qs(urlsplit(authorization).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] and query["nonce"]

    with httpx.Client(timeout=20) as browser:
        page = browser.get(authorization)
        assert page.status_code == 200
        form = LoginForm()
        form.feed(page.text)
        assert form.action, "Keycloak 未返回预期的登录表单"
        assert urlsplit(form.action).netloc == "127.0.0.1:8080"
        assert urlsplit(form.action).path.startswith(f"/realms/{keycloak['realm']}/")
        # 本地 Keycloak 返回 Secure Cookie，HTTPX 不会在 HTTP 上自动回传。
        # 仅在受控的本地身份服务表单请求中显式带回，不改变应用 Cookie 策略。
        cookies = "; ".join(f"{c.name}={c.value}" for c in browser.cookies.jar)
        response = browser.post(
            form.action,
            headers={"Cookie": cookies},
            data={
                **form.fields,
                "username": username,
                "password": keycloak["password"],
            },
        )
        assert response.status_code == 302, "Keycloak 登录未完成"
        callback = response.headers["location"]
        assert urlsplit(callback).path == "/auth/callback"
        assert "code" in parse_qs(urlsplit(callback).query)
    return callback


def test_real_oidc_two_users(server, keycloak, database):
    if keycloak is None:
        pytest.skip("设置 RUN_OIDC_TESTS=1 后运行真实 Keycloak 登录")
    ids = []
    try:
        with (
            httpx.Client(base_url=server["origin"], timeout=20) as alice,
            httpx.Client(base_url=server["origin"], timeout=20) as bob,
        ):
            for client, name in ((alice, "alice"), (bob, "bob")):
                callback = authorize(client, keycloak, name)
                response = client.get(callback)
                assert response.status_code == 303
                cookie = response.headers["set-cookie"].lower()
                assert "httponly" in cookie and "samesite=lax" in cookie
                identity = client.get("/auth/me")
                assert identity.status_code == 200
                ids.append(UUID(identity.json()["user_id"]))
                client.headers.update(
                    {
                        "Origin": server["origin"],
                        "X-CSRF-Token": identity.json()["csrf_token"],
                    }
                )
                # 一次登录回调只能消费一次。
                assert client.get(callback).status_code == 401

            assert ids[0] != ids[1]
            old_cookie = alice.cookies.get("inroom_session")
            old_csrf = alice.headers["X-CSRF-Token"]
            assert alice.get(authorize(alice, keycloak, "alice")).status_code == 303
            identity = alice.get("/auth/me").json()
            assert UUID(identity["user_id"]) == ids[0]
            assert identity["csrf_token"] != old_csrf
            alice.headers["X-CSRF-Token"] = identity["csrf_token"]
            with httpx.Client(base_url=server["origin"]) as old_session:
                old_session.cookies.set("inroom_session", old_cookie)
                assert old_session.get("/auth/me").status_code == 401
            created = alice.post("/v1/preparations")
            assert created.status_code == 201
            path = f"/v1/preparations/{created.json()['id']}"
            assert bob.get(path).status_code == 404
            assert (
                bob.post(
                    f"{path}/cancel", json={"expected_state_version": 1}
                ).status_code
                == 404
            )
            assert alice.get(path).status_code == 200
            with Session(database) as db:
                users = db.scalars(select(User).where(User.id.in_(ids))).all()
                assert len(users) == 2
                assert all(user.issuer == keycloak["issuer"] for user in users)
            assert alice.post("/auth/logout").status_code == 204
            assert alice.get("/auth/me").status_code == 401
    finally:
        # 测试拥有独立 realm，清理该 realm 的所有本地身份和数据。
        with Session(database) as db, db.begin():
            owned = select(User.id).where(User.issuer == keycloak["issuer"])
            db.execute(delete(Preparation).where(Preparation.owner_id.in_(owned)))
            db.execute(delete(LoginSession).where(LoginSession.user_id.in_(owned)))
            db.execute(delete(User).where(User.issuer == keycloak["issuer"]))


def test_invalid_state(server):
    with httpx.Client(base_url=server["origin"]) as client:
        response = client.get(
            "/auth/callback", params={"code": "invalid", "state": "invalid"}
        )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
