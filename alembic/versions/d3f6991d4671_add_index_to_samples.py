"""add index to samples

Revision ID: d3f6991d4671
Revises: 9169a7c5bda3
Create Date: 2022-08-14 22:59:38.685376

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "d3f6991d4671"
down_revision = "9169a7c5bda3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(None, "samples", ["sku_index"])


def downgrade() -> None:
    pass
