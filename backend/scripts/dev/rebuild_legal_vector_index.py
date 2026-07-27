"""Rebuild approved legal knowledge vector index for local Phase 1 baseline."""

from __future__ import annotations

import asyncio
import json

from payroll_copilot.application.ports.ai_capabilities import AICapability
from payroll_copilot.application.services.legal_rag_indexer import LegalRagIndexer
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import (
    get_legal_knowledge_store,
)
from payroll_copilot.infrastructure.rag.vector_store_factory import (
    get_legal_vector_store,
    reset_legal_vector_store,
)


async def main() -> None:
    settings = get_settings()
    router = AIProviderRouter(settings)
    route = router.route(AICapability.ASSISTANT)
    reset_legal_vector_store()
    vectors = get_legal_vector_store()
    store = get_legal_knowledge_store()
    before = store.vector_health()
    print("BEFORE", before.status, before.chunk_count)
    indexer = LegalRagIndexer(
        rules_path=settings.legal_rules_path,
        model=route.provider,
        store=store,
        vector_store=vectors,
        embedding_model_name=getattr(settings, "ollama_embedding_model", "configured_provider")
        or "configured_provider",
    )
    result = await indexer.rebuild_all()
    after = store.vector_health()
    print("RESULT", json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print("AFTER", after.status, after.chunk_count, after.embedding_model)


if __name__ == "__main__":
    asyncio.run(main())
