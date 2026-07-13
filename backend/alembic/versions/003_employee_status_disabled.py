"""Add disabled value to employeestatus enum."""

from alembic import op

revision = "003_employee_status_disabled"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE employeestatus ADD VALUE IF NOT EXISTS 'disabled'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely; leave in place.
    pass
