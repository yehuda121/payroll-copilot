"""Add DISABLED value to employeestatus enum.

PostgreSQL/SQLAlchemy use enum *names* for this type (ACTIVE, ON_LEAVE, TERMINATED).
"""

from alembic import op

revision = "003_employee_status_disabled"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Match existing employeestatus labels (UPPER_SNAKE names used by SQLAlchemy Enum).
    op.execute("ALTER TYPE employeestatus ADD VALUE IF NOT EXISTS 'DISABLED'")
    # Safety if an earlier revision mistakenly added the StrEnum *value*.
    op.execute("ALTER TYPE employeestatus ADD VALUE IF NOT EXISTS 'disabled'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely; leave in place.
    pass
