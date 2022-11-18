"""change price column type to int

Revision ID: ac8256c291d4
Revises: d3f6991d4671
Create Date: 2022-10-07 21:16:06.677110

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ac8256c291d4"
down_revision = "d3f6991d4671"
branch_labels = None
depends_on = None


def upgrade() -> None:
    db = op.get_bind()

    print(">>> Adding price_cents column")
    op.add_column("samples", sa.Column("price_cents", sa.Integer(), nullable=True))
    print(">>> Filling price_cents column")
    db.execute("UPDATE samples SET price_cents = 100 * price")

    with op.batch_alter_table("samples") as batch_op:
        print(">>> Marking price_cents column non-nullable")
        batch_op.alter_column("price_cents", nullable=False)
        print(">>> Dropping price column")
        batch_op.drop_column("price")


def downgrade() -> None:
    pass
