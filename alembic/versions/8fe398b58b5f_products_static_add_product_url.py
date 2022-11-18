"""products_static: add product url

Revision ID: 8fe398b58b5f
Revises: ac4b7897c153
Create Date: 2022-06-07 21:11:10.517608

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "8fe398b58b5f"
down_revision = "ac4b7897c153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products_static", sa.Column("url", sa.String()))


def downgrade() -> None:
    op.drop_column("products_static", "url")
