import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_upgrade_preserves_data_and_failure_rolls_back(
    database_url, migrate, tmp_path,
):
    schema = f"migration_test_{uuid4().hex}"
    admin = create_engine(database_url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))

    url = make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    url_text = url.render_as_string(hide_password=False)
    engine = create_engine(url)

    try:
        migrate(url_text, "0001")
        user_id, preparation_id = uuid4(), uuid4()
        with engine.begin() as db:
            db.execute(
                text("INSERT INTO users VALUES (:id, 'migration-test', 'user')"),
                {"id": user_id},
            )
            db.execute(
                text("INSERT INTO preparations VALUES (:id, :owner, 'DRAFT')"),
                {"id": preparation_id, "owner": user_id},
            )

        migrate(url_text)
        with engine.connect() as db:
            assert db.execute(
                text("SELECT status, state_version FROM preparations")
            ).one() == ("DRAFT", 1)
            assert db.execute(
                text("SELECT to_regclass('jobs')")
            ).scalar_one() is not None
            current_revision = db.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        invalid = migrate(url_text, "does_not_exist", check=False)
        assert invalid.returncode != 0

        # 在临时迁移链末尾追加一次故意失败的迁移。
        source = Path(__file__).resolve().parents[2] / "migrations"
        scripts = tmp_path / "migrations"
        shutil.copytree(
            source, scripts, ignore=shutil.ignore_patterns("__pycache__"),
        )
        config = tmp_path / "alembic.ini"
        config.write_text(
            f"[alembic]\nscript_location = {scripts.as_posix()}\n",
            encoding="utf-8",
        )
        (scripts / "versions" / "test_failure.py").write_text(
            "from alembic import op\n"
            'revision = "test_failure"\n'
            f"down_revision = {current_revision!r}\n"
            "def upgrade():\n"
            '    op.execute("CREATE TABLE partial_write (id INTEGER)")\n'
            '    op.execute("CREATE TABLE users (id INTEGER)")\n',
            encoding="utf-8",
        )

        failed = migrate(url_text, config=config, check=False)
        assert failed.returncode != 0

        with engine.connect() as db:
            assert db.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == current_revision
            assert db.execute(
                text("SELECT to_regclass('partial_write')")
            ).scalar_one() is None
            assert db.execute(
                text("SELECT count(*) FROM preparations")
            ).scalar_one() == 1
    finally:
        engine.dispose()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()