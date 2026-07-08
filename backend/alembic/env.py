"""Alembic migration environment.

DATABASE_URL (environment) is the single source of truth for the DB target.
FastAPI Settings and Alembic must always share that same variable.

Falls back to alembic.ini ``sqlalchemy.url`` only when DATABASE_URL is unset
(typical host-local convenience). Inside Docker, Compose injects DATABASE_URL
and that value always wins.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from payroll_copilot.infrastructure.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """Prefer DATABASE_URL from the environment; otherwise use alembic.ini."""
    env_url = os.environ.get("DATABASE_URL", "").strip()
    if env_url:
        return env_url
    ini_url = config.get_main_option("sqlalchemy.url")
    if not ini_url:
        raise RuntimeError(
            "DATABASE_URL is not set and alembic.ini has no sqlalchemy.url. "
            "Set DATABASE_URL so Alembic and FastAPI target the same database."
        )
    return ini_url


def _configure_sqlalchemy_url() -> str:
    url = _resolve_database_url()
    # Escape % for ConfigParser interpolation safety.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return url


def run_migrations_offline() -> None:
    url = _configure_sqlalchemy_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    _configure_sqlalchemy_url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
