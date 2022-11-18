"""create initial tables

Revision ID: ac4b7897c153
Revises:
Create Date: 2022-03-20 14:32:35.216741

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ac4b7897c153"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products_static",
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("is_in_clearance", sa.Boolean(), nullable=True),
        sa.Column("last_listed", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("index", name=op.f("pk_products_static")),
        sa.UniqueConstraint("code", name=op.f("uq_products_static_code")),
    )
    op.create_index(
        op.f("ix_products_static_index"), "products_static", ["index"], unique=True
    )
    op.create_table(
        "products_dynamic",
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("sample_time", sa.DateTime(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("in_promo", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["code"],
            ["products_static.code"],
            name=op.f("fk_products_dynamic_code_products_static"),
        ),
        sa.PrimaryKeyConstraint("index", name=op.f("pk_products_dynamic")),
    )
    op.create_index(
        op.f("ix_products_dynamic_code"), "products_dynamic", ["code"], unique=False
    )
    op.create_index(
        op.f("ix_products_dynamic_index"), "products_dynamic", ["index"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_products_dynamic_index"), table_name="products_dynamic")
    op.drop_index(op.f("ix_products_dynamic_code"), table_name="products_dynamic")
    op.drop_table("products_dynamic")
    op.drop_index(op.f("ix_products_static_index"), table_name="products_static")
    op.drop_table("products_static")
