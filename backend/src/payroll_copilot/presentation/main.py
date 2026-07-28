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
from payroll_copilot.domain.rules import ensure_validation_rules_registered
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.router import api_router

# Same registration entry as Celery worker — keep API/worker rule sets identical.
ensure_validation_rules_registered()


async def _bootstrap_legal_vector_index_if_empty() -> None:
    """Populate Chroma when the persistent volume is empty (common after first compose up).

    Fail-open: never block API startup if embeddings or catalog are unavailable.
    """
    settings = get_settings()
    if not bool(getattr(settings, "legal_rag_enabled", True)):
        return
    try:
        from payroll_copilot.application.ports.ai_capabilities import AICapability
        from payroll_copilot.application.services.legal_rag_indexer import LegalRagIndexer
        from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
        from payroll_copilot.infrastructure.persistence.legal_knowledge_store import (
            get_legal_knowledge_store,
        )
        from payroll_copilot.infrastructure.rag.vector_store_factory import (
            get_legal_vector_store,
        )

        store = get_legal_knowledge_store()
        health = store.vector_health()
        vectors = get_legal_vector_store()
        live_count: int | None = None
        if hasattr(vectors, "count"):
            try:
                live_count = int(vectors.count())
            except Exception:  # noqa: BLE001
                live_count = None
        # Prefer live Chroma/numpy count. Stale Dynamo health must not skip rebuild.
        if live_count is not None:
            if live_count > 0:
                return
        else:
            chunk_count = int(getattr(health, "chunk_count", 0) or 0)
            if chunk_count > 0 and getattr(health, "status", None) != "empty":
                return

        model = AIProviderRouter(settings).provider_for(AICapability.ASSISTANT)
        embedding_model_name = (
            getattr(model, "_embedding_model", None)
            or getattr(settings, "ollama_embedding_model", None)
            or getattr(settings, "openai_embedding_model", None)
            or "configured_provider"
        )
        indexer = LegalRagIndexer(
            rules_path=settings.legal_rules_path,
            model=model,
            store=store,
            vector_store=vectors,
            embedding_model_name=str(embedding_model_name),
        )
        result = await indexer.rebuild_all()
        structlog.get_logger().info(
            "legal_vector_index_bootstrapped",
            chunk_count=result.get("chunk_count"),
            status=result.get("status"),
            backend=result.get("backend"),
        )
    except Exception as exc:  # noqa: BLE001 — fail-open
        structlog.get_logger().warning(
            "legal_vector_index_bootstrap_skipped",
            error=f"{type(exc).__name__}: {exc}",
        )


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
    await _bootstrap_legal_vector_index_if_empty()
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
