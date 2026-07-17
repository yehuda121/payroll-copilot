"""Database session management (legacy SQLAlchemy — optional).

Runtime persistence uses DynamoDB. PostgreSQL is only needed for Alembic/legacy
tooling when DATABASE_URL is set.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from payroll_copilot.infrastructure.config.settings import get_settings

settings = get_settings()

engine: AsyncEngine | None
async_session_factory: async_sessionmaker[AsyncSession] | None

if settings.database_url:
    engine = create_async_engine(
        settings.database_url_str,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
    )
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
else:
    engine = None
    async_session_factory = None


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if async_session_factory is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Runtime persistence uses DynamoDB; "
            "set DATABASE_URL only for legacy SQLAlchemy / Alembic tooling."
        )
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
