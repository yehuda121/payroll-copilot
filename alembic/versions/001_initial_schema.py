"""Initial database schema.

Revision ID: 001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Tables created via metadata for consistency
    from payroll_copilot.infrastructure.persistence.models import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from payroll_copilot.infrastructure.persistence.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
