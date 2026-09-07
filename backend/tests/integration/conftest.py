import json
import os
import secrets
import socket
import subprocess
import sys
import time
from base64 import b64encode
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from itsdangerous import TimestampSigner
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.db.models import LoginSession, Preparation, User

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database_url():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("设置 TEST_DATABASE_URL 后运行 PostgreSQL 集成测试")
    url = make_url(value)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "inroom_test":
        pytest.fail("集成测试只允许本地 inroom_test 数据库")
    return value


@pytest.fixture(scope="session")
def migrate():
    def run(url, revision="head", config=None, check=True):
        env = os.environ.copy()
        env.update(DATABASE_URL=url, PYTHONIOENCODING="utf-8")
        args = [sys.executable, "-m", "alembic"]
        if config:
            args += ["-c", str(config)]
        return subprocess.run(
            [*args, "upgrade", revision],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=check,
        )

    return run


@pytest.fixture(scope="session")
def database(database_url, migrate):
    migrate(database_url)
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def keycloak():
    if os.environ.get("RUN_OIDC_TESTS") != "1":
        yield None
        return

    realm = f"inroom-test-{uuid4().hex}"
    secret = secrets.token_urlsafe(32)
    password = secrets.token_urlsafe(24)
    with httpx.Client(base_url="http://127.0.0.1:8080", timeout=20) as admin:
        response = admin.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": os.environ.get("KEYCLOAK_ADMIN_USER", "admin"),
                "password": os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin"),
            },
        )
        response.raise_for_status()
        admin.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        response = admin.post(
            "/admin/realms",
            json={
                "realm": realm,
                "enabled": True,
                "sslRequired": "none",
                "clients": [
                    {
                        "clientId": "inroom-test",
                        "secret": secret,
                        "publicClient": False,
                        "standardFlowEnabled": True,
                        "directAccessGrantsEnabled": False,
                        "redirectUris": [],
                    }
                ],
                "users": [
                    {
                        "username": name,
                        "enabled": True,
                        "emailVerified": True,
                        "email": f"{name}@example.test",
                        "firstName": name,
                        "lastName": "Test",
                        "credentials": [
                            {
                                "type": "password",
                                "value": password,
                                "temporary": False,
                            }
                        ],
                    }
                    for name in ("alice", "bob")
                ],
            },
        )
        response.raise_for_status()
        try:
            yield {
                "issuer": f"http://127.0.0.1:8080/realms/{realm}",
                "client_id": "inroom-test",
                "secret": secret,
                "password": password,
                "admin": admin,
                "realm": realm,
            }
        finally:
            admin.delete(f"/admin/realms/{realm}").raise_for_status()


@pytest.fixture(scope="session")
def server(database, database_url, keycloak, tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    secret = secrets.token_urlsafe(32)
    env = os.environ.copy()
    env.update(
        APP_ENV="test",
        DATABASE_URL=database_url,
        APP_ORIGIN=origin,
        SESSION_SECRET=secret,
        LOG_LEVEL="WARNING",
        DEV_IDENTITY_ENABLED="false",
    )
    if keycloak:
        env.update(
            OIDC_ISSUER=keycloak["issuer"],
            OIDC_CLIENT_ID=keycloak["client_id"],
            OIDC_CLIENT_SECRET=keycloak["secret"],
        )
        # 只给本次临时 realm 设置本次服务的精确回调地址。
        admin = keycloak["admin"]
        clients = admin.get(
            f"/admin/realms/{keycloak['realm']}/clients",
            params={"clientId": keycloak["client_id"]},
        ).json()
        admin.put(
            f"/admin/realms/{keycloak['realm']}/clients/{clients[0]['id']}",
            json={"redirectUris": [f"{origin}/auth/callback"]},
        ).raise_for_status()

    log_path = tmp_path_factory.mktemp("api") / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--loop",
                "asyncio:SelectorEventLoop",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            with httpx.Client(base_url=origin, timeout=1) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail("测试 API 启动失败；检查临时 server.log")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("测试 API 启动超时")
            yield {"origin": origin, "secret": secret}
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture
def users(database, server):
    ids = []
    clients = []
    try:
        with Session(database) as db, db.begin():
            for _ in range(2):
                user = User(issuer="integration-test", subject=uuid4().hex)
                db.add(user)
                db.flush()
                ids.append(user.id)
                login = LoginSession(
                    user_id=user.id,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
                db.add(login)
                db.flush()
                payload = b64encode(
                    json.dumps(
                        {
                            "login_id": str(login.id),
                            "csrf": "test-csrf",
                        }
                    ).encode()
                )
                cookie = TimestampSigner(server["secret"]).sign(payload).decode()
                client = httpx.Client(base_url=server["origin"], timeout=15)
                client.cookies.set("inroom_session", cookie)
                client.headers.update(
                    {
                        "Origin": server["origin"],
                        "X-CSRF-Token": "test-csrf",
                    }
                )
                clients.append(client)
        yield clients
    finally:
        for client in clients:
            client.close()
        with Session(database) as db, db.begin():
            db.execute(delete(Preparation).where(Preparation.owner_id.in_(ids)))
            db.execute(delete(LoginSession).where(LoginSession.user_id.in_(ids)))
            db.execute(delete(User).where(User.id.in_(ids)))
