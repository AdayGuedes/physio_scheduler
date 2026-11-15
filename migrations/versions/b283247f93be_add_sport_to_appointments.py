
"""Add sport to appointments

Revision ID: b283247f93be
Revises: 055b3eb75177
Create Date: 2026-11-15 15:55:09.390400

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b283247f93be"
down_revision = "055b3eb75177"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sport", sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.drop_column("sport")
