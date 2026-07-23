"""Add optional payroll_accountant_id on employees."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "006_employee_payroll_accountant"
down_revision = "005_extraction_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("payroll_accountant_id", UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "payroll_accountant_id")
