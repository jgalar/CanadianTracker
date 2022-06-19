"""add product sku

Revision ID: 4e2a96338a6c
Revises: 8fe398b58b5f
Create Date: 2022-06-12 17:14:19.328685

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4e2a96338a6c"
down_revision = "8fe398b58b5f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products_static", sa.Column("sku", sa.String()))


def downgrade():
    op.drop_column("products_static", "sku")
