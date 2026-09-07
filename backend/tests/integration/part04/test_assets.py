from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import Preparation
from backend.preparations.models import ResumeAsset


def test_upgrade_preserves_preparation(asset_database):
    engine, alice, _, preparation_id = asset_database
    with Session(engine) as db:
        preparation = db.get(Preparation, preparation_id)
        assert preparation is not None
        assert preparation.owner_id == alice
        assert preparation.status == "DRAFT"
        assert preparation.state_version == 3
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0


def test_owner_can_save_and_reload_asset(asset_database):
    engine, alice, _, preparation_id = asset_database
    key = uuid4().hex
    with Session(engine) as db, db.begin():
        asset = ResumeAsset(
            owner_id=alice,
            preparation_id=preparation_id,
            object_key=key,
            filename="测试简历.pdf",
            size_bytes=123,
        )
        db.add(asset)
        db.flush()
        asset_id = asset.id

    with Session(engine) as db:
        saved = db.get(ResumeAsset, asset_id)
        assert saved is not None
        assert saved.owner_id == alice
        assert saved.preparation_id == preparation_id
        assert saved.object_key == key
        assert saved.filename == "测试简历.pdf"
        assert saved.size_bytes == 123
        assert saved.created_at.tzinfo is not None


def test_database_rejects_cross_user_reference(asset_database):
    engine, _, bob, preparation_id = asset_database
    with pytest.raises(IntegrityError) as error:
        with Session(engine) as db, db.begin():
            db.add(
                ResumeAsset(
                    owner_id=bob,
                    preparation_id=preparation_id,
                    object_key=uuid4().hex,
                    filename="test.pdf",
                    size_bytes=123,
                )
            )

    assert error.value.orig.diag.constraint_name == "fk_resume_assets_preparation_owner"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0


def test_duplicate_storage_key_rolls_back_transaction(asset_database):
    engine, alice, _, preparation_id = asset_database
    key = uuid4().hex
    with pytest.raises(IntegrityError) as error:
        with Session(engine) as db, db.begin():
            for filename in ["first.pdf", "second.pdf"]:
                db.add(
                    ResumeAsset(
                        owner_id=alice,
                        preparation_id=preparation_id,
                        object_key=key,
                        filename=filename,
                        size_bytes=123,
                    )
                )
                db.flush()

    assert error.value.orig.sqlstate == "23505"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ResumeAsset)) == 0
