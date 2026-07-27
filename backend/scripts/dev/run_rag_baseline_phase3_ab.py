"""Phase 3 A/B: run benchmark with legal rerank enabled; compare to Phase 1 baseline."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

# Ensure rerank is on for this process before settings are cached.
os.environ["LEGAL_RAG_RERANK_ENABLED"] = "true"
os.environ.setdefault("LEGAL_RAG_RETRIEVAL_TOP_K", "20")
os.environ.setdefault("LEGAL_RAG_RERANK_TOP_N", "5")
os.environ.setdefault("LEGAL_RAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
os.environ.setdefault("LEGAL_RAG_RERANK_TIMEOUT_MS", "120000")
os.environ.setdefault("LEGAL_RAG_RERANK_DEVICE", "cpu")

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
from payroll_copilot.infrastructure.rag.legal_reranker_factory import build_legal_chunk_reranker
from payroll_copilot.infrastructure.rag.vector_store_factory import (
    get_legal_vector_store,
    reset_legal_vector_store,
)

PHASE1_BASELINE = Path("data/rag_eval_baselines/baseline_91cbde6f-ca42-4cba-a83c-3fce49ce08dd.json")


def _metric(run: dict, key: str):
    block = (run.get(key) or {}) if isinstance(run, dict) else {}
    return block.get("value"), block.get("status")


async def main() -> None:
    # Clear settings LRU so env overrides apply.
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.legal_rag_rerank_enabled is True

    store = get_legal_knowledge_store()
    if store.get_active_eval_lock():
        store.release_eval_lock()

    reset_legal_vector_store()
    vectors = get_legal_vector_store()
    router = AIProviderRouter(settings)
    route = router.route(AICapability.ASSISTANT)
    model = route.provider
    reranker = build_legal_chunk_reranker(settings)
    retriever = VersionAwareLegalRetriever(
        model=model,
        store=store,
        vector_store=vectors,
        reranker=reranker,
        rerank_enabled=True,
        retrieval_top_k=int(settings.legal_rag_retrieval_top_k),
        rerank_top_n=int(settings.legal_rag_rerank_top_n),
        rerank_timeout_ms=int(settings.legal_rag_rerank_timeout_ms),
    )

    # Warm model outside case loop timing.
    warm_ms = None
    if reranker is not None and hasattr(getattr(reranker, "_inner", None), "ensure_loaded"):
        t0 = time.perf_counter()
        reranker._inner.ensure_loaded()  # type: ignore[attr-defined]
        warm_ms = (time.perf_counter() - t0) * 1000.0

    baseline_config = {
        "phase": "phase3_ab_after_rerank",
        "rerank_enabled": True,
        "legal_rag_retrieval_top_k": settings.legal_rag_retrieval_top_k,
        "legal_rag_rerank_top_n": settings.legal_rag_rerank_top_n,
        "legal_rag_rerank_model": settings.legal_rag_rerank_model,
        "legal_rag_rerank_timeout_ms": settings.legal_rag_rerank_timeout_ms,
        "legal_rag_rerank_device": settings.legal_rag_rerank_device or "cpu",
        "model_warm_ms": warm_ms,
        "compare_to_baseline": str(PHASE1_BASELINE),
    }

    service = RagEvaluationService(
        store=store,
        retriever=retriever,
        model=model,
        ragas=RagasAdapter(enabled=settings.ragas_enabled),
        baseline_config=baseline_config,
        retrieval_top_k=int(settings.legal_rag_rerank_top_n or 5),
    )

    t_run = time.perf_counter()
    run = await service.run_evaluation(triggered_by="phase3_ab_cli")
    elapsed_ms = (time.perf_counter() - t_run) * 1000.0
    cases = store.list_evaluation_cases(run.run_id)

    before = json.loads(PHASE1_BASELINE.read_text(encoding="utf-8"))
    before_run = before["run"]
    before_cases = {c["case_id"]: c for c in before.get("cases") or []}

    keys = [
        "hit_rate_at_5",
        "recall_at_5",
        "mrr",
        "temporal_accuracy",
        "faithfulness",
        "context_recall",
        "answer_relevancy",
        "context_precision",
    ]
    comparison = {}
    for key in keys:
        b_val, b_st = _metric(before_run, key)
        a_val, a_st = _metric(run.model_dump(mode="json"), key)
        delta = None
        if isinstance(b_val, (int, float)) and isinstance(a_val, (int, float)):
            delta = float(a_val) - float(b_val)
        comparison[key] = {
            "before": b_val,
            "after": a_val,
            "delta": delta,
            "before_status": b_st,
            "after_status": a_st,
        }

    order_changed = 0
    first_rank_improved = 0
    first_rank_regressed = 0
    fallback_count = 0
    per_case = []
    for c in cases:
        d = c.retrieval_diagnostics or {}
        if d.get("order_changed"):
            order_changed += 1
        if d.get("rerank_fallback"):
            fallback_count += 1
        b = before_cases.get(c.case_id) or {}
        b_rank = b.get("first_relevant_rank")
        a_rank = c.first_relevant_rank
        rank_delta = None
        if b_rank is not None and a_rank is not None:
            rank_delta = int(b_rank) - int(a_rank)  # positive = improved (lower rank)
            if rank_delta > 0:
                first_rank_improved += 1
            elif rank_delta < 0:
                first_rank_regressed += 1
        elif b_rank is None and a_rank is not None:
            first_rank_improved += 1
            rank_delta = "miss_to_hit"
        elif b_rank is not None and a_rank is None:
            first_rank_regressed += 1
            rank_delta = "hit_to_miss"
        per_case.append(
            {
                "case_id": c.case_id,
                "order_changed": bool(d.get("order_changed")),
                "rerank_fallback": bool(d.get("rerank_fallback")),
                "before_first_relevant_rank": b_rank,
                "after_first_relevant_rank": a_rank,
                "rank_delta": rank_delta,
                "before_hit_at_5": b.get("hit_at_5"),
                "after_hit_at_5": c.hit_at_5,
                "before_retrieved": b.get("retrieved_rule_ids"),
                "after_retrieved": c.retrieved_rule_ids,
            }
        )

    # Decision heuristics (primary: Hit/Recall/MRR; do not celebrate precision alone).
    hit_delta = comparison["hit_rate_at_5"]["delta"]
    recall_delta = comparison["recall_at_5"]["delta"]
    mrr_delta = comparison["mrr"]["delta"]
    primary_regressed = any(
        isinstance(x, float) and x < -1e-9 for x in (hit_delta, recall_delta, mrr_delta)
    )
    primary_improved = any(
        isinstance(x, float) and x > 1e-9 for x in (hit_delta, recall_delta, mrr_delta)
    )
    if primary_regressed and not primary_improved:
        decision = "REJECT RERANKER"
    elif primary_regressed and primary_improved:
        decision = "NEEDS TUNING"
    elif primary_improved and fallback_count == 0:
        decision = "ACCEPT RERANKER"
    elif not primary_improved and not primary_regressed:
        # Flat primary metrics: only accept if ranking/faithfulness clearly help without harm.
        faith_delta = comparison["faithfulness"]["delta"]
        if isinstance(faith_delta, float) and faith_delta > 0.02 and fallback_count == 0:
            decision = "NEEDS TUNING"
        else:
            decision = "NEEDS TUNING"
    else:
        decision = "NEEDS TUNING"

    out = {
        "executive": decision,
        "phase1_baseline": str(PHASE1_BASELINE),
        "after_run_id": run.run_id,
        "elapsed_ms": elapsed_ms,
        "model_warm_ms": warm_ms,
        "comparison": comparison,
        "ranking_changes": {
            "order_changed_cases": order_changed,
            "first_relevant_rank_improved": first_rank_improved,
            "first_relevant_rank_regressed": first_rank_regressed,
            "rerank_fallback_count": fallback_count,
        },
        "per_case": per_case,
        "run": run.model_dump(mode="json"),
    }

    out_dir = Path("data/rag_eval_baselines")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"phase3_ab_{run.run_id}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("DECISION", decision)
    print("SNAPSHOT", path)
    print("COMPARISON", json.dumps(comparison, indent=2))
    print("RANKING", json.dumps(out["ranking_changes"], indent=2))
    print("WARM_MS", warm_ms, "ELAPSED_MS", elapsed_ms)


if __name__ == "__main__":
    asyncio.run(main())
