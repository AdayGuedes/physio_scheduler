"""New physio_id column in appointments

Revision ID: 055b3eb75177
Revises: c8b1da291972
Create Date: 2026-10-05 12:34:34.473729

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "055b3eb75177"
down_revision = "c8b1da291972"
branch_labels = None
depends_on = None


def upgrade():
    # Intentional guard: no physio can be inferred for existing appointments, and
    # the table is empty in every environment (no route creates appointments yet).
    connection = op.get_bind()
    total = connection.execute(sa.text("SELECT COUNT(*) FROM appointments")).scalar()

    if total > 0:
        raise RuntimeError(
            f"Appointments has {total} rows; delete them or assign a physio before upgrading."
        )

    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("physio_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key(
            "fk_appointments_physio_id_users", "users", ["physio_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.drop_constraint("fk_appointments_physio_id_users", type_="foreignkey")
        batch_op.drop_column("physio_id")
