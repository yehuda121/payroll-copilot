"""Phase 1: run RAG baseline evaluation and write a reproducible snapshot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from payroll_copilot.application.ports.ai_capabilities import AICapability
from payroll_copilot.application.services.rag_evaluation import RagEvaluationService
from payroll_copilot.application.services.ragas_adapter import RagasAdapter
from payroll_copilot.application.services.version_aware_legal_retriever import (
    VersionAwareLegalRetriever,
)
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
    store = get_legal_knowledge_store()
    health = store.vector_health()
    reset_legal_vector_store()
    vectors = get_legal_vector_store()
    model = None
    answer_provider = None
    answer_model = None
    emb_provider = None
    emb_model_setting = getattr(settings, "ollama_embedding_model", None)
    ragas_import_error = None
    ragas_version = None
    try:
        from payroll_copilot.application.services.ragas_adapter import (
            _ensure_ragas_langchain_compat,
        )

        _ensure_ragas_langchain_compat()
        import ragas as _ragas

        ragas_version = getattr(_ragas, "__version__", None)
    except Exception as exc:  # noqa: BLE001
        ragas_import_error = f"{type(exc).__name__}: {exc}"
    try:
        router = AIProviderRouter(settings)
        route = router.route(AICapability.ASSISTANT)
        model = route.provider
        answer_provider = route.provider_name
        answer_model = route.model
        emb_route = router.route(AICapability.EMBEDDINGS)
        emb_provider = emb_route.provider_name
    except Exception as exc:  # noqa: BLE001
        print("MODEL_ROUTE_ERROR", type(exc).__name__, exc)

    embed_probe: dict = {"ok": False, "error": None, "dims": None}
    if model is not None:
        try:
            vecs = await model.embed(["baseline probe"])
            embed_probe = {
                "ok": True,
                "error": None,
                "dims": len(vecs[0]) if vecs and vecs[0] else 0,
            }
        except Exception as exc:  # noqa: BLE001
            embed_probe = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "dims": None,
            }

    baseline_config = {
        "phase": "baseline_before_rerank",
        "legal_rag_enabled": bool(settings.legal_rag_enabled),
        "legal_vector_backend": settings.legal_vector_backend,
        "legal_vector_collection": settings.legal_vector_collection,
        "legal_vector_persist_path": settings.legal_vector_persist_path,
        "vector_index_status": health.status,
        "vector_chunk_count": health.chunk_count,
        "vector_backend_runtime": getattr(vectors, "BACKEND_NAME", type(vectors).__name__),
        "vector_embedding_model_recorded": health.embedding_model,
        "embedding_capability_provider": emb_provider,
        "ollama_embedding_model_setting": emb_model_setting,
        "retriever_model_provider": answer_provider,
        "retriever_model": answer_model,
        "embed_probe": embed_probe,
        "rag_top_k_setting": settings.rag_top_k,
        "rag_min_confidence_setting": settings.rag_min_confidence,
        "ragas_enabled_setting": settings.ragas_enabled,
        "ragas_import_error": ragas_import_error,
        "ragas_version": ragas_version,
        "rerank_enabled": False,
        "note_embedding_runtime": (
            "VersionAwareLegalRetriever.embed uses the ASSISTANT ModelProvider "
            "instance; OllamaProvider.embed calls ollama_embedding_model."
        ),
    }

    service = RagEvaluationService(
        store=store,
        retriever=VersionAwareLegalRetriever(
            model=model, store=store, vector_store=vectors
        ),
        model=model,
        ragas=RagasAdapter(enabled=settings.ragas_enabled),
        baseline_config=baseline_config,
        retrieval_top_k=int(settings.rag_top_k or 5),
    )
    run = await service.run_evaluation(triggered_by="phase1_baseline_cli")
    cases = store.list_evaluation_cases(run.run_id)

    vector_path_failed = run.failed_cases == run.case_count and run.case_count > 0
    ragas_ok = any(
        c.context_precision.status == "ok" or c.faithfulness.status == "ok" for c in cases
    )
    if (
        not embed_probe["ok"]
        or health.chunk_count <= 0
        or vector_path_failed
        or not ragas_ok
    ):
        executive = "BASELINE BLOCKED"
    else:
        executive = "VALID BASELINE"

    out = {
        "executive": executive,
        "blockers": {
            "empty_vector_index": health.chunk_count <= 0,
            "embed_probe_failed": not embed_probe["ok"],
            "embed_probe_error": embed_probe.get("error"),
            "ragas_import_error": ragas_import_error,
            "all_cases_failed": vector_path_failed,
            "no_ragas_ok_scores": not ragas_ok,
        },
        "run": run.model_dump(mode="json"),
        "cases": [
            {
                "case_id": c.case_id,
                "expected_rule_ids": c.expected_rule_ids,
                "retrieved_rule_ids": c.retrieved_rule_ids,
                "retrieval_scores": c.retrieval_scores,
                "first_relevant_rank": c.first_relevant_rank,
                "hit_at_5": c.hit_at_5,
                "recall_at_5": c.recall_at_5,
                "mrr": c.mrr,
                "retrieval_mode": c.retrieval_mode,
                "fallback_occurred": (c.retrieval_diagnostics or {}).get(
                    "fallback_occurred"
                ),
                "retrieval_diagnostics_reason": (c.retrieval_diagnostics or {}).get(
                    "reason"
                ),
                "faithfulness": c.faithfulness.model_dump(),
                "context_precision": c.context_precision.model_dump(),
                "context_recall": c.context_recall.model_dump(),
                "answer_relevancy": c.answer_relevancy.model_dump(),
                "temporal_pass": c.temporal_pass,
                "temporal_detail": c.temporal_detail,
                "error": c.error,
                "status": c.status,
            }
            for c in cases
        ],
    }

    out_dir = Path("data/rag_eval_baselines")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"baseline_{run.run_id}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXECUTIVE", executive)
    print("RUN_ID", run.run_id)
    print("SNAPSHOT", path)
    print(
        "CASES",
        run.case_count,
        "completed",
        run.completed_cases,
        "failed",
        run.failed_cases,
    )
    print("BLOCKERS", json.dumps(out["blockers"], ensure_ascii=False, indent=2))
    print("CONFIG", json.dumps(run.baseline_config, ensure_ascii=False, indent=2))
    print(
        "AGG",
        json.dumps(
            {
                "context_precision": run.context_precision.model_dump(),
                "context_recall": run.context_recall.model_dump(),
                "faithfulness": run.faithfulness.model_dump(),
                "answer_relevancy": run.answer_relevancy.model_dump(),
                "temporal_accuracy": run.temporal_accuracy.model_dump(),
                "hit_rate_at_5": run.hit_rate_at_5.model_dump(),
                "recall_at_5": run.recall_at_5.model_dump(),
                "mrr": run.mrr.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    for c in cases[:5]:
        print("CASE", c.case_id, c.status, c.error, c.retrieval_mode)


if __name__ == "__main__":
    asyncio.run(main())
