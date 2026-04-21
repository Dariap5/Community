"""normalize scheduled task timestamp column

Revision ID: 002
Revises: 001
Create Date: 2026-04-21 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _scheduled_tasks_columns() -> set[str]:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'scheduled_tasks'
            """
        )
    )
    return {row[0] for row in result}


def upgrade() -> None:
    columns = _scheduled_tasks_columns()
    if "run_at" in columns and "execute_at" not in columns:
        op.execute(sa.text("ALTER TABLE scheduled_tasks RENAME COLUMN run_at TO execute_at"))


def downgrade() -> None:
    columns = _scheduled_tasks_columns()
    if "execute_at" in columns and "run_at" not in columns:
        op.execute(sa.text("ALTER TABLE scheduled_tasks RENAME COLUMN execute_at TO run_at"))
