import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.api import create_app
from backend.core.config import Settings
from backend.db.models import User
from backend.jobs.models import Job

BACKEND = Path(__file__).resolve().parents[3]


@pytest.fixture
def process_database(database_url, migrate):
    # 真实 Worker 自己配置连接参数，使用独立数据库隔离整个进程。
    name = f"inroom_test_part03_{uuid4().hex}"
    admin = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as db:
        db.execute(text(f'CREATE DATABASE "{name}"'))
    url = (
        make_url(database_url).set(database=name).render_as_string(hide_password=False)
    )
    engine = create_engine(url)
    try:
        migrate(url)
        yield url, engine
    finally:
        engine.dispose()
        with admin.connect() as db:
            db.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def eventually(check, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for worker state")


def test_real_workers_recovery_cancel_health_and_exit(process_database, tmp_path):
    url, engine = process_database
    processes = []
    logs = []
    env = os.environ.copy()
    env.update(
        APP_ENV="test", DATABASE_URL=url, PYTHONIOENCODING="utf-8", LOG_LEVEL="INFO"
    )

    def launch():
        log = (tmp_path / f"worker-{len(processes)}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.worker"],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        processes.append(process)
        return process

    with Session(engine) as db, db.begin():
        user = User(issuer="process-test", subject=uuid4().hex)
        db.add(user)
        db.flush()
        owner = user.id

    def enqueue(seconds, fail=False):
        with Session(engine, expire_on_commit=False) as db, db.begin():
            job = Job(
                owner_id=owner,
                kind="demo",
                payload={"seconds": seconds, "fail": fail},
                dedupe_key=uuid4().hex,
            )
            db.add(job)
            db.flush()
            return job.id

    def read(job_id):
        with Session(engine) as db:
            job = db.get(Job, job_id)
            return {
                "status": job.status,
                "attempts": job.attempts,
                "token": job.fencing_token,
                "worker": job.locked_by,
                "lease": job.lease_until,
            }

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        session_secret="process-health-test",
        log_level="CRITICAL",
        dev_identity_enabled=False,
    )
    try:
        with TestClient(
            create_app(settings),
            backend_options={"loop_factory": asyncio.SelectorEventLoop},
        ) as client:
            assert client.get("/health/worker").status_code == 503
            first = launch()
            eventually(lambda: client.get("/health/worker").json().get("workers") == 1)
            job_id = enqueue(60)
            eventually(lambda: read(job_id)["status"] == "running")
            original = read(job_id)
            second = launch()
            eventually(lambda: client.get("/health/worker").json().get("workers") == 2)

            # 等一次真实的十秒续租，第二个 Worker 不能抢走任务。
            eventually(lambda: read(job_id)["lease"] > original["lease"], timeout=15)
            assert read(job_id)["attempts"] == 1
            assert read(job_id)["worker"] == original["worker"]

            first.kill()
            first.wait(timeout=5)
            # 加速租约过期；进程确实已被杀死，不等待剩余三十秒。
            with engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE jobs SET lease_until = clock_timestamp() - interval '1 second', payload = '{\"seconds\": 0}'::jsonb WHERE id = :id"
                    ),
                    {"id": job_id},
                )
            eventually(lambda: read(job_id)["status"] == "completed")
            recovered = read(job_id)
            assert recovered["attempts"] == 2
            assert recovered["token"] == original["token"] + 1
            eventually(lambda: _inbox_count(engine) == 1)

            # 用真实登录 Cookie 和 CSRF 走取消接口。
            import json
            from base64 import b64encode
            from datetime import UTC, datetime, timedelta

            from itsdangerous import TimestampSigner

            from backend.db.models import LoginSession

            with Session(engine) as db, db.begin():
                login = LoginSession(
                    user_id=owner, expires_at=datetime.now(UTC) + timedelta(hours=1)
                )
                db.add(login)
                db.flush()
                cookie = (
                    TimestampSigner("process-health-test")
                    .sign(
                        b64encode(
                            json.dumps(
                                {"login_id": str(login.id), "csrf": "part03"}
                            ).encode()
                        )
                    )
                    .decode()
                )
            client.cookies.set("inroom_session", cookie)
            cancelling = enqueue(60)
            eventually(lambda: read(cancelling)["status"] == "running")
            response = client.post(
                f"/jobs/{cancelling}/cancel",
                headers={"Origin": settings.app_origin, "X-CSRF-Token": "part03"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "cancelled"
            # 后续任务完成证明 runner 已退出被取消的处理器。
            following = enqueue(0)
            eventually(lambda: read(following)["status"] == "completed", timeout=15)
            assert read(cancelling)["status"] == "cancelled"
            assert read(cancelling)["attempts"] == 1

            failing = enqueue(0, fail=True)
            eventually(lambda: read(failing)["status"] == "failed")
            assert read(failing)["attempts"] == 3
            response = client.get(f"/jobs/{failing}")
            assert response.status_code == 200
            assert response.json()["status"] == "failed"
            assert response.json()["error"]

            second.kill()
            second.wait(timeout=5)
            with engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE worker_heartbeats SET last_seen = clock_timestamp() - interval '31 seconds'"
                    )
                )
            assert client.get("/health/worker").status_code == 503
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for log in logs:
            log.close()


def _inbox_count(engine):
    with engine.connect() as db:
        return db.execute(text("SELECT count(*) FROM inbox")).scalar_one()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows 的 terminate 是强制终止；SIGTERM 优雅退出在 Linux CI 验证",
)
def test_sigterm_finishes_current_job(process_database, tmp_path):
    url, engine = process_database
    with Session(engine, expire_on_commit=False) as db, db.begin():
        user = User(issuer="shutdown-test", subject=uuid4().hex)
        db.add(user)
        db.flush()
        job = Job(
            owner_id=user.id,
            kind="demo",
            payload={"seconds": 2},
            dedupe_key=uuid4().hex,
        )
        db.add(job)
        db.flush()
        job_id = job.id
    env = os.environ.copy()
    env.update(APP_ENV="test", DATABASE_URL=url)
    with (tmp_path / "shutdown.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.worker"],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:

            def running():
                with Session(engine) as db:
                    return (
                        db.scalar(select(Job.status).where(Job.id == job_id))
                        == "running"
                    )

            eventually(running)
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=10) == 0
            with Session(engine) as db:
                assert db.get(Job, job_id).status == "completed"
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
