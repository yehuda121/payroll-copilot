"""Developer-admin RAG Evaluation APIs — separate from AI Monitoring and Analytics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from payroll_copilot.application.dto.legal_knowledge import EvaluationCaseResult, EvaluationRun
from payroll_copilot.application.ports.ai_capabilities import AICapability
from payroll_copilot.application.services.rag_evaluation import RagEvaluationService
from payroll_copilot.application.services.ragas_adapter import RagasAdapter
from payroll_copilot.application.services.version_aware_legal_retriever import VersionAwareLegalRetriever
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import get_legal_knowledge_store
from payroll_copilot.presentation.api.security import AuthPrincipal, get_auth_principal

router = APIRouter()


async def require_developer_admin(
    principal: AuthPrincipal = Depends(get_auth_principal),  # noqa: B008
) -> AuthPrincipal:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_role_required",
                "message": "Developer admin role required.",
            },
        )
    return principal


def _service() -> RagEvaluationService:
    settings = get_settings()
    store = get_legal_knowledge_store()
    model = None
    answer_provider = None
    answer_model = None
    embedding_provider = None
    embedding_model = None
    try:
        router = AIProviderRouter(settings)
        # Production eval + Legal RAG retrieve embeds via the same ModelProvider
        # instance passed into VersionAwareLegalRetriever (ASSISTANT capability).
        route = router.route(AICapability.ASSISTANT)
        model = route.provider
        answer_provider = route.provider_name
        answer_model = route.model
        emb_route = router.route(AICapability.EMBEDDINGS)
        embedding_provider = emb_route.provider_name
        embedding_model = emb_route.model
    except Exception:  # noqa: BLE001
        model = None
    from payroll_copilot.infrastructure.rag.legal_reranker_factory import (
        build_legal_chunk_reranker,
    )

    rerank_enabled = bool(getattr(settings, "legal_rag_rerank_enabled", False))
    reranker = build_legal_chunk_reranker(settings) if rerank_enabled else None
    retriever = VersionAwareLegalRetriever(
        model=model,
        store=store,
        reranker=reranker,
        rerank_enabled=rerank_enabled,
        retrieval_top_k=int(getattr(settings, "legal_rag_retrieval_top_k", 20) or 20),
        rerank_top_n=int(getattr(settings, "legal_rag_rerank_top_n", 5) or 5),
        rerank_timeout_ms=int(getattr(settings, "legal_rag_rerank_timeout_ms", 250) or 250),
    )
    health = store.vector_health()
    baseline_config = {
        "phase": "baseline_before_rerank",
        "legal_rag_enabled": bool(getattr(settings, "legal_rag_enabled", True)),
        "legal_vector_backend": getattr(settings, "legal_vector_backend", None),
        "legal_vector_collection": getattr(settings, "legal_vector_collection", None),
        "legal_vector_persist_path": getattr(settings, "legal_vector_persist_path", None),
        "vector_index_status": getattr(health, "status", None),
        "vector_chunk_count": getattr(health, "chunk_count", None),
        "vector_embedding_model_recorded": getattr(health, "embedding_model", None),
        "embedding_capability_provider": embedding_provider,
        "embedding_capability_model": embedding_model,
        "retriever_model_provider": answer_provider,
        "retriever_model": answer_model,
        "note_embedding_runtime": (
            "VersionAwareLegalRetriever.embed uses the ASSISTANT ModelProvider "
            "instance passed to the eval service (same as chat legal RAG)."
        ),
        "rag_top_k_setting": getattr(settings, "rag_top_k", 5),
        "rag_min_confidence_setting": getattr(settings, "rag_min_confidence", None),
        "ragas_enabled_setting": bool(getattr(settings, "ragas_enabled", True)),
        "rerank_enabled": rerank_enabled,
        "legal_rag_retrieval_top_k": int(
            getattr(settings, "legal_rag_retrieval_top_k", 20) or 20
        ),
        "legal_rag_rerank_top_n": int(getattr(settings, "legal_rag_rerank_top_n", 5) or 5),
        "legal_rag_rerank_model": str(
            getattr(settings, "legal_rag_rerank_model", "") or ""
        )
        or None,
        "legal_rag_rerank_timeout_ms": int(
            getattr(settings, "legal_rag_rerank_timeout_ms", 250) or 250
        ),
    }
    return RagEvaluationService(
        store=store,
        retriever=retriever,
        model=model,
        ragas=RagasAdapter(enabled=settings.ragas_enabled),
        baseline_config=baseline_config,
        retrieval_top_k=int(getattr(settings, "rag_top_k", 5) or 5),
    )


@router.get("/summary")
async def evaluation_summary(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    store = get_legal_knowledge_store()
    runs = [r for r in store.list_evaluation_runs(limit=20) if r.status == "COMPLETED"]
    latest = runs[0] if runs else None
    adapter = RagasAdapter(enabled=get_settings().ragas_enabled)
    return {
        "latest_run": latest.model_dump(mode="json") if latest else None,
        "ragas_available": adapter.available,
        "ragas_version": adapter.version,
        "ragas_import_error": adapter._import_error,
    }


@router.post("/runs", response_model=EvaluationRun)
async def start_evaluation(
    principal: AuthPrincipal = Depends(require_developer_admin),
) -> EvaluationRun:
    try:
        return await _service().run_evaluation(triggered_by=str(principal.user_id))
    except RuntimeError as exc:
        if str(exc) == "evaluation_already_running":
            raise HTTPException(status_code=409, detail="evaluation_already_running") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs", response_model=list[EvaluationRun])
async def list_runs(
    _: AuthPrincipal = Depends(require_developer_admin),
    limit: int = 50,
) -> list[EvaluationRun]:
    return get_legal_knowledge_store().list_evaluation_runs(limit=limit)


@router.get("/runs/{run_id}", response_model=EvaluationRun)
async def get_run(
    run_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> EvaluationRun:
    run = get_legal_knowledge_store().get_evaluation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="evaluation_run_not_found")
    return run


@router.get("/runs/{run_id}/cases", response_model=list[EvaluationCaseResult])
async def list_cases(
    run_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> list[EvaluationCaseResult]:
    cases = get_legal_knowledge_store().list_evaluation_cases(run_id)
    if not cases and get_legal_knowledge_store().get_evaluation_run(run_id) is None:
        raise HTTPException(status_code=404, detail="evaluation_run_not_found")
    return cases


@router.get("/runs/{run_id}/cases/{case_id}", response_model=EvaluationCaseResult)
async def get_case(
    run_id: str,
    case_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> EvaluationCaseResult:
    for case in get_legal_knowledge_store().list_evaluation_cases(run_id):
        if case.case_id == case_id:
            return case
    raise HTTPException(status_code=404, detail="case_not_found")


@router.get("/compare")
async def compare_runs(
    run_a: str,
    run_b: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    store = get_legal_knowledge_store()
    a = store.get_evaluation_run(run_a)
    b = store.get_evaluation_run(run_b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="evaluation_run_not_found")

    def _delta(x, y):
        if x is None or y is None or x.status != "ok" or y.status != "ok":
            return None
        if x.value is None or y.value is None:
            return None
        return y.value - x.value

    warn = a.dataset_version != b.dataset_version
    cases_a = {c.case_id: c for c in store.list_evaluation_cases(run_a)}
    cases_b = {c.case_id: c for c in store.list_evaluation_cases(run_b)}
    improved: list[str] = []
    regressed: list[str] = []
    for case_id in set(cases_a) & set(cases_b):
        ca, cb = cases_a[case_id], cases_b[case_id]
        if ca.faithfulness.value is not None and cb.faithfulness.value is not None:
            if cb.faithfulness.value > ca.faithfulness.value + 0.02:
                improved.append(case_id)
            elif cb.faithfulness.value < ca.faithfulness.value - 0.02:
                regressed.append(case_id)
    return {
        "run_a": a.model_dump(mode="json"),
        "run_b": b.model_dump(mode="json"),
        "dataset_version_mismatch": warn,
        "deltas": {
            "faithfulness": _delta(a.faithfulness, b.faithfulness),
            "context_precision": _delta(a.context_precision, b.context_precision),
            "context_recall": _delta(a.context_recall, b.context_recall),
            "answer_relevancy": _delta(a.answer_relevancy, b.answer_relevancy),
            "temporal_accuracy": _delta(a.temporal_accuracy, b.temporal_accuracy),
        },
        "improved_cases": improved,
        "regressed_cases": regressed,
    }


@router.get("/benchmark")
async def get_benchmark(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    data = _service().load_benchmark()
    return {
        "dataset_version": data.get("dataset_version"),
        "case_count": len([c for c in data.get("cases") or [] if c.get("enabled", True)]),
        "cases": [
            {
                "case_id": c.get("case_id"),
                "question": c.get("question"),
                "effective_date": c.get("effective_date"),
                "tags": c.get("tags"),
                "enabled": c.get("enabled", True),
            }
            for c in data.get("cases") or []
        ],
    }
