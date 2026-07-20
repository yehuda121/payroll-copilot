"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from payroll_copilot.infrastructure.config.production_guards import (
    is_production_env,
    validate_production_settings,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.router import api_router

# Import rule modules to register them in the global registry
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    validate_production_settings(settings)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if settings.log_format == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    # Fail fast before routes are mounted when APP_ENV is production.
    validate_production_settings(settings)

    production = is_production_env(settings)
    docs_url = None if production else "/docs"
    redoc_url = None if production else "/redoc"
    openapi_url = None if production else f"{settings.api_prefix}/openapi.json"

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/ready")
    async def ready() -> dict[str, str | bool]:
        settings = get_settings()
        production = is_production_env(settings)

        db_ok = True
        try:
            from payroll_copilot.infrastructure.persistence.dynamodb.client import get_dynamo_table

            await get_dynamo_table().describe()
        except Exception:
            db_ok = False

        redis_ok = True
        try:
            import redis

            from payroll_copilot.infrastructure.config.service_resolver import (
                get_resolved_redis_url,
            )

            client = redis.Redis.from_url(
                get_resolved_redis_url(settings),
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            client.ping()
        except Exception:
            redis_ok = False

        # Production requires DynamoDB + Redis before accepting traffic.
        # Local/dev remains convenient: DynamoDB alone is enough for ready.
        if production:
            is_ready = db_ok and redis_ok
        else:
            is_ready = db_ok

        return {
            "status": "ready" if is_ready else "not_ready",
            "database": db_ok,
            "redis": redis_ok,
            "persistence": "dynamodb",
        }

    return app


app = create_app()
