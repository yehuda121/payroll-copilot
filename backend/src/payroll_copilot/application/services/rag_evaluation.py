"""RAG Evaluation vertical — real production RAG path + RAGAS + temporal accuracy."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from payroll_copilot.application.dto.legal_knowledge import (
    EvaluationCaseResult,
    EvaluationRun,
    RagEvalMetricValue,
)
from payroll_copilot.application.ports import Message, ModelProvider
from payroll_copilot.application.services.ragas_adapter import RagasAdapter
from payroll_copilot.application.services.version_aware_legal_retriever import VersionAwareLegalRetriever
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore

logger = logging.getLogger(__name__)

# Modes that are not a valid vector-RAG baseline (must not silently score).
_INVALID_VECTOR_MODES = frozenset({"yaml_fallback", "unavailable", "unknown", ""})


class RagEvaluationService:
    def __init__(
        self,
        *,
        store: LegalKnowledgeStore,
        retriever: VersionAwareLegalRetriever,
        model: ModelProvider | None,
        ragas: RagasAdapter | None = None,
        benchmark_path: Path | str | None = None,
        baseline_config: dict[str, Any] | None = None,
        retrieval_top_k: int = 5,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._model = model
        self._ragas = ragas or RagasAdapter()
        self._baseline_config = dict(baseline_config or {})
        self._retrieval_top_k = max(1, int(retrieval_top_k))
        if benchmark_path is None:
            root = Path(__file__).resolve().parents[4]
            benchmark_path = root / "config" / "rag_eval" / "benchmark_v1.json"
        self._benchmark_path = Path(benchmark_path)

    def load_benchmark(self) -> dict[str, Any]:
        if not self._benchmark_path.exists():
            return {"dataset_version": "missing", "cases": []}
        return json.loads(self._benchmark_path.read_text(encoding="utf-8"))

    async def run_evaluation(self, *, triggered_by: str | None = None) -> EvaluationRun:
        if self._store.get_active_eval_lock():
            raise RuntimeError("evaluation_already_running")

        dataset = self.load_benchmark()
        provider = getattr(self._model, "_provider_name", None) or getattr(
            self._model, "provider_name", None
        )
        model_name = getattr(self._model, "_default_model", None) or getattr(
            self._model, "model_name", None
        )
        run = EvaluationRun(
            run_id=str(uuid4()),
            dataset_version=str(dataset.get("dataset_version") or "unknown"),
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            provider=str(provider) if provider else None,
            model=str(model_name) if model_name else None,
            prompt_version="payroll_assistant_grounded_v1",
            case_count=0,
            triggered_by=triggered_by,
            baseline_config={
                **self._baseline_config,
                "benchmark_path": str(self._benchmark_path),
                "dataset_version": str(dataset.get("dataset_version") or "unknown"),
                "retrieval_top_k": self._retrieval_top_k,
                "rerank_enabled": False,
                "answer_provider": str(provider) if provider else None,
                "answer_model": str(model_name) if model_name else None,
                "ragas_available": bool(self._ragas.available),
                "ragas_version": self._ragas.version,
                "ragas_import_error": getattr(self._ragas, "_import_error", None),
                "ragas_judge": getattr(self._ragas, "judge_config", None),
            },
        )
        if not self._store.acquire_eval_lock(run.run_id):
            raise RuntimeError("evaluation_already_running")

        self._store.save_evaluation_run(run)
        cases_out: list[EvaluationCaseResult] = []
        try:
            enabled_cases = [c for c in dataset.get("cases") or [] if c.get("enabled", True)]
            run.case_count = len(enabled_cases)
            self._store.save_evaluation_run(run)

            for case in enabled_cases:
                result = await self._run_case(case)
                cases_out.append(result)
                if result.error:
                    run.failed_cases += 1
                else:
                    run.completed_cases += 1
                self._store.save_evaluation_run(run)

            run.faithfulness = _aggregate([c.faithfulness for c in cases_out])
            run.context_precision = _aggregate([c.context_precision for c in cases_out])
            run.context_recall = _aggregate([c.context_recall for c in cases_out])
            run.answer_relevancy = _aggregate([c.answer_relevancy for c in cases_out])
            run.temporal_accuracy = _temporal_aggregate(cases_out)
            run.hit_rate_at_5 = _aggregate_bool([c.hit_at_5 for c in cases_out])
            run.recall_at_5 = _aggregate_float([c.recall_at_5 for c in cases_out])
            run.mrr = _aggregate_float([c.mrr for c in cases_out])
            run.status = "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            self._store.save_evaluation_run(run)
            self._store.save_evaluation_cases(run.run_id, cases_out)
            return run
        except Exception as exc:  # noqa: BLE001
            run.status = "FAILED"
            run.error = f"{type(exc).__name__}: {exc}"
            run.completed_at = datetime.now(timezone.utc)
            self._store.save_evaluation_run(run)
            self._store.save_evaluation_cases(run.run_id, cases_out)
            raise
        finally:
            self._store.release_eval_lock()

    async def _run_case(self, case: dict[str, Any]) -> EvaluationCaseResult:
        case_id = str(case.get("case_id") or uuid4())
        question = str(case.get("question") or "")
        reference = str(case.get("reference_answer") or "")
        expected_rules = [str(x) for x in (case.get("expected_rule_ids") or [])]
        eff_raw = case.get("effective_date")
        effective: date | None = None
        if isinstance(eff_raw, str) and eff_raw:
            try:
                effective = date.fromisoformat(eff_raw[:10])
            except ValueError:
                effective = None

        result = EvaluationCaseResult(
            case_id=case_id,
            question=question,
            reference_answer=reference,
            effective_date=effective,
            expected_rule_ids=expected_rules,
            status="running",
        )
        try:
            retrieval = await self._retriever.retrieve(
                question,
                effective_date=effective,
                top_k=self._retrieval_top_k,
            )
            hits = retrieval.get("hits") or []
            diagnostics = dict(retrieval.get("diagnostics") or {})
            result.retrieval_diagnostics = diagnostics
            result.retrieval_mode = str(diagnostics.get("retrieval_mode") or "unknown")

            # Persist retrieval ordering metadata without inventing scores.
            result.retrieval_scores = [
                float(h["score"]) for h in hits if h.get("score") is not None
            ]
            result.retrieved_rule_ids = [str(h.get("rule_id")) for h in hits if h.get("rule_id")]
            result.retrieved_versions = [
                f"{h.get('rule_id')}@v{h.get('rule_version')}" for h in hits if h.get("rule_id")
            ]
            hit_metrics = _retrieval_metrics(
                expected_rules=expected_rules,
                retrieved_rule_ids=result.retrieved_rule_ids,
                k=self._retrieval_top_k,
            )
            result.hit_at_5 = hit_metrics["hit_at_k"]
            result.recall_at_5 = hit_metrics["recall_at_k"]
            result.mrr = hit_metrics["mrr"]
            result.first_relevant_rank = hit_metrics["first_relevant_rank"]
            diagnostics["hit_at_k"] = hit_metrics["hit_at_k"]
            diagnostics["recall_at_k"] = hit_metrics["recall_at_k"]
            diagnostics["mrr"] = hit_metrics["mrr"]
            diagnostics["first_relevant_rank"] = hit_metrics["first_relevant_rank"]
            diagnostics["fallback_occurred"] = result.retrieval_mode in _INVALID_VECTOR_MODES
            result.retrieval_diagnostics = diagnostics

            if result.retrieval_mode in _INVALID_VECTOR_MODES:
                reason = (
                    "yaml_fallback_not_allowed_in_eval"
                    if result.retrieval_mode == "yaml_fallback"
                    else f"vector_retrieval_invalid:{result.retrieval_mode}"
                )
                result.error = (
                    "evaluation_used_yaml_fallback"
                    if result.retrieval_mode == "yaml_fallback"
                    else f"evaluation_vector_unavailable:{diagnostics.get('reason') or result.retrieval_mode}"
                )
                result.status = "error"
                unavailable = RagEvalMetricValue(status="unavailable", reason=reason)
                result.faithfulness = unavailable
                result.context_precision = unavailable
                result.context_recall = unavailable
                result.answer_relevancy = unavailable
                return result

            contexts = [str(h.get("text") or "") for h in hits if h.get("text")]
            result.retrieved_contexts = contexts
            result.sources = [
                {
                    "title": h.get("title"),
                    "rule_id": h.get("rule_id"),
                    "rule_version": h.get("rule_version"),
                    "source_reference": h.get("source_reference"),
                    "valid_from": h.get("valid_from"),
                    "valid_to": h.get("valid_to"),
                    "authority_level": h.get("authority_level"),
                    "score": h.get("score"),
                    "chunk_id": h.get("chunk_id"),
                }
                for h in hits
            ]

            # Temporal Retrieval Accuracy (deterministic, separate from RAGAS)
            result.temporal_pass, result.temporal_detail = _temporal_check(
                expected_rules=expected_rules,
                hits=hits,
                effective_date=effective,
            )

            result.generated_answer = await self._generate(question, contexts, hits)
            metrics = self._ragas.score_case(
                question=question,
                reference_answer=reference,
                generated_answer=result.generated_answer,
                retrieved_contexts=contexts,
            )
            result.faithfulness = metrics["faithfulness"]
            result.context_precision = metrics["context_precision"]
            result.context_recall = metrics["context_recall"]
            result.answer_relevancy = metrics["answer_relevancy"]
            result.status = "completed"
            return result
        except Exception as exc:  # noqa: BLE001 — isolate case failures
            logger.exception("rag_eval_case_failed", extra={"case_id": case_id})
            result.error = f"{type(exc).__name__}: {exc}"
            result.status = "error"
            result.faithfulness = RagEvalMetricValue(status="unavailable", reason="case_error")
            result.context_precision = RagEvalMetricValue(status="unavailable", reason="case_error")
            result.context_recall = RagEvalMetricValue(status="unavailable", reason="case_error")
            result.answer_relevancy = RagEvalMetricValue(status="unavailable", reason="case_error")
            return result

    async def _generate(self, question: str, contexts: list[str], hits: list[dict[str, Any]]) -> str:
        if self._model is None:
            if not contexts:
                return "Approved legal evidence was unavailable for this question."
            return "Based on approved retrieved evidence:\n" + "\n".join(f"- {c[:400]}" for c in contexts[:3])

        citations = []
        for h in hits[:5]:
            citations.append(
                f"{h.get('title')} v{h.get('rule_version')} "
                f"({h.get('valid_from')}..{h.get('valid_to') or 'current'}) "
                f"ref={h.get('source_reference')}"
            )
        prompt = (
            "Answer ONLY from the approved retrieved legal evidence below. "
            "Do not invent law, tax calculations, or sources. "
            "If evidence is insufficient, say so clearly.\n\n"
            f"Question: {question}\n\n"
            f"Retrieved evidence:\n{chr(10).join(contexts[:5])}\n\n"
            f"Citations metadata:\n{chr(10).join(citations)}"
        )
        result = await self._model.complete(
            [
                Message(role="system", content="You are a grounded payroll legal explainer."),
                Message(role="user", content=prompt),
            ],
            temperature=0.0,
            max_tokens=800,
        )
        return result.content or ""


def _retrieval_metrics(
    *,
    expected_rules: list[str],
    retrieved_rule_ids: list[str],
    k: int,
) -> dict[str, Any]:
    """HitRate@k / Recall@k / MRR from expected rule ids (no external deps)."""
    if not expected_rules:
        return {
            "hit_at_k": None,
            "recall_at_k": None,
            "mrr": None,
            "first_relevant_rank": None,
        }
    expected = set(expected_rules)
    top = retrieved_rule_ids[:k]
    hits = [rid for rid in top if rid in expected]
    first_rank: int | None = None
    for idx, rid in enumerate(top, start=1):
        if rid in expected:
            first_rank = idx
            break
    return {
        "hit_at_k": bool(hits),
        "recall_at_k": (len(set(hits)) / len(expected)) if expected else None,
        "mrr": (1.0 / first_rank) if first_rank else 0.0,
        "first_relevant_rank": first_rank,
    }


def _temporal_check(
    *,
    expected_rules: list[str],
    hits: list[dict[str, Any]],
    effective_date: date | None,
) -> tuple[bool | None, str]:
    if not expected_rules:
        return None, "no_expected_rule_ids"
    if effective_date is None:
        return None, "no_effective_date"
    if not hits:
        return False, "no_hits"
    # Pass if at least one hit is an expected rule and eligible for effective_date.
    for hit in hits:
        rule_id = str(hit.get("rule_id") or "")
        if rule_id not in expected_rules:
            continue
        vf_raw = hit.get("valid_from")
        vt_raw = hit.get("valid_to")
        try:
            vf = date.fromisoformat(str(vf_raw)[:10]) if vf_raw else date.min
        except ValueError:
            return False, f"invalid_valid_from:{vf_raw}"
        try:
            vt = date.fromisoformat(str(vt_raw)[:10]) if vt_raw else None
        except ValueError:
            return False, f"invalid_valid_to:{vt_raw}"
        eligible = vf <= effective_date and (vt is None or vt >= effective_date)
        if eligible:
            return True, f"matched:{rule_id}@v{hit.get('rule_version')}"
        return False, f"ineligible_version:{rule_id}@v{hit.get('rule_version')}"
    return False, "expected_rule_not_retrieved"


def _aggregate(values: list[RagEvalMetricValue]) -> RagEvalMetricValue:
    import math

    ok = [
        v.value
        for v in values
        if v.status == "ok"
        and v.value is not None
        and not (isinstance(v.value, float) and math.isnan(v.value))
    ]
    if not ok:
        reasons = [v.reason or v.status for v in values if v.status != "ok"]
        nan_count = sum(
            1
            for v in values
            if v.status == "ok"
            and isinstance(v.value, float)
            and math.isnan(v.value)
        )
        if nan_count and not reasons:
            reasons = [f"nan_scores:{nan_count}"]
        return RagEvalMetricValue(
            status="unavailable",
            reason="; ".join(reasons[:5]) or "no_ok_scores",
        )
    return RagEvalMetricValue(value=sum(ok) / len(ok), status="ok")


def _aggregate_bool(values: list[bool | None]) -> RagEvalMetricValue:
    scored = [v for v in values if v is not None]
    if not scored:
        return RagEvalMetricValue(status="unavailable", reason="no_retrieval_metric_cases")
    return RagEvalMetricValue(value=sum(1 for v in scored if v) / len(scored), status="ok")


def _aggregate_float(values: list[float | None]) -> RagEvalMetricValue:
    import math

    scored = [
        v
        for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    if not scored:
        return RagEvalMetricValue(status="unavailable", reason="no_retrieval_metric_cases")
    return RagEvalMetricValue(value=sum(scored) / len(scored), status="ok")


def _temporal_aggregate(cases: list[EvaluationCaseResult]) -> RagEvalMetricValue:
    scored = [c for c in cases if c.temporal_pass is not None]
    if not scored:
        return RagEvalMetricValue(status="unavailable", reason="no_temporal_cases")
    passed = sum(1 for c in scored if c.temporal_pass)
    return RagEvalMetricValue(value=passed / len(scored), status="ok")
