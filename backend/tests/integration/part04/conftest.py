from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


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
