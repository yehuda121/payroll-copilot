"""Add extraction confirmation and validation→extraction linkage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005_extraction_confirmation"
down_revision = "004_user_employee_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column(
            "confirmation_status",
            sa.String(length=32),
            nullable=False,
            server_default="review_required",
        ),
    )
    op.add_column(
        "document_extractions",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_extractions",
        sa.Column("confirmed_by", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_extractions_confirmed_by_users",
        "document_extractions",
        "users",
        ["confirmed_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "validation_runs",
        sa.Column("extraction_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_validation_runs_extraction_id", "validation_runs", ["extraction_id"])
    op.create_foreign_key(
        "fk_validation_runs_extraction_id",
        "validation_runs",
        "document_extractions",
        ["extraction_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_validation_runs_extraction_id", "validation_runs", type_="foreignkey")
    op.drop_index("ix_validation_runs_extraction_id", table_name="validation_runs")
    op.drop_column("validation_runs", "extraction_id")

    op.drop_constraint(
        "fk_document_extractions_confirmed_by_users",
        "document_extractions",
        type_="foreignkey",
    )
    op.drop_column("document_extractions", "confirmed_by")
    op.drop_column("document_extractions", "confirmed_at")
    op.drop_column("document_extractions", "confirmation_status")
