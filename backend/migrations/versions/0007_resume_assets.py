import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_preparations_id_owner",
        "preparations",
        ["id", "owner_id"],
    )

    op.create_table(
        "resume_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preparation_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["preparation_id", "owner_id"],
            ["preparations.id", "preparations.owner_id"],
            name="fk_resume_assets_preparation_owner",
        ),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_resume_assets_preparation_id", "resume_assets", ["preparation_id"]
    )
    op.create_index("ix_resume_assets_owner_id", "resume_assets", ["owner_id"])


def downgrade() -> None:
    op.drop_table("resume_assets")
    op.drop_constraint(
        "uq_preparations_id_owner",
        "preparations",
        type_="unique",
    )
