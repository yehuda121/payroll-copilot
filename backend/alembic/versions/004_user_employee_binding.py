"""Add users.employee_id binding to employees (nullable for non-employee roles)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "004_user_employee_binding"
down_revision = "003_employee_status_disabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("employee_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_users_employee_id", "users", ["employee_id"])
    op.create_foreign_key(
        "fk_users_employee_id_employees",
        "users",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_employee_id_employees", "users", type_="foreignkey")
    op.drop_index("ix_users_employee_id", table_name="users")
    op.drop_column("users", "employee_id")
