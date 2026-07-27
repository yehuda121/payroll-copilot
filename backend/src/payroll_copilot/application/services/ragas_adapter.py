"""RAGAS adapter boundary — never fabricates scores; UNAVAILABLE on errors/missing evidence."""

from __future__ import annotations

import logging
from typing import Any

from payroll_copilot.application.dto.legal_knowledge import RagEvalMetricValue

logger = logging.getLogger(__name__)

# Pinned conceptually; actual import verified at runtime.
RAGAS_VERSION_PIN = "0.2.15"


class RagasAdapter:
    """Thin adapter around RAGAS metrics. Unit tests mock this class."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._ragas_version: str | None = None
        self._import_error: str | None = None
        if enabled:
            self._try_import()

    def _try_import(self) -> None:
        try:
            import ragas  # noqa: F401

            self._ragas_version = getattr(ragas, "__version__", RAGAS_VERSION_PIN)
        except Exception as exc:  # noqa: BLE001
            self._import_error = f"{type(exc).__name__}: {exc}"
            self._ragas_version = None

    @property
    def available(self) -> bool:
        return self._enabled and self._ragas_version is not None

    @property
    def version(self) -> str | None:
        return self._ragas_version

    def score_case(
        self,
        *,
        question: str,
        reference_answer: str,
        generated_answer: str,
        retrieved_contexts: list[str],
    ) -> dict[str, RagEvalMetricValue]:
        """Compute four required metrics. Missing evidence → UNAVAILABLE (never 0)."""
        base = {
            "faithfulness": RagEvalMetricValue(status="unavailable", reason="not_computed"),
            "context_precision": RagEvalMetricValue(status="unavailable", reason="not_computed"),
            "context_recall": RagEvalMetricValue(status="unavailable", reason="not_computed"),
            "answer_relevancy": RagEvalMetricValue(status="unavailable", reason="not_computed"),
        }
        if not self.available:
            reason = self._import_error or "ragas_not_installed"
            return {k: RagEvalMetricValue(status="unavailable", reason=reason) for k in base}

        if not generated_answer.strip():
            return {
                k: RagEvalMetricValue(status="unavailable", reason="generated_answer_empty")
                for k in base
            }
        if not retrieved_contexts:
            # Faithfulness/precision/recall need contexts; answer relevancy may still run.
            partial = {
                "faithfulness": RagEvalMetricValue(
                    status="unavailable", reason="no_retrieved_contexts"
                ),
                "context_precision": RagEvalMetricValue(
                    status="unavailable", reason="no_retrieved_contexts"
                ),
                "context_recall": RagEvalMetricValue(
                    status="unavailable", reason="no_retrieved_contexts"
                ),
            }
            ar = self._safe_metric(
                "answer_relevancy",
                question=question,
                answer=generated_answer,
                contexts=retrieved_contexts,
                reference=reference_answer,
            )
            return {**partial, "answer_relevancy": ar}

        return {
            "faithfulness": self._safe_metric(
                "faithfulness",
                question=question,
                answer=generated_answer,
                contexts=retrieved_contexts,
                reference=reference_answer,
            ),
            "context_precision": self._safe_metric(
                "context_precision",
                question=question,
                answer=generated_answer,
                contexts=retrieved_contexts,
                reference=reference_answer,
            ),
            "context_recall": self._safe_metric(
                "context_recall",
                question=question,
                answer=generated_answer,
                contexts=retrieved_contexts,
                reference=reference_answer,
            ),
            "answer_relevancy": self._safe_metric(
                "answer_relevancy",
                question=question,
                answer=generated_answer,
                contexts=retrieved_contexts,
                reference=reference_answer,
            ),
        }

    def _safe_metric(
        self,
        name: str,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> RagEvalMetricValue:
        try:
            value = self._compute_single(
                name,
                question=question,
                answer=answer,
                contexts=contexts,
                reference=reference,
            )
            if value is None:
                return RagEvalMetricValue(status="unavailable", reason=f"{name}_returned_none")
            return RagEvalMetricValue(value=float(value), status="ok")
        except Exception as exc:  # noqa: BLE001
            logger.warning("ragas_metric_failed", extra={"metric": name, "error": str(exc)})
            return RagEvalMetricValue(
                status="error",
                reason=f"{type(exc).__name__}: {exc}",
            )

    def _compute_single(
        self,
        name: str,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> float | None:
        """Call RAGAS evaluate for a single-row dataset.

        Isolated so unit tests can monkeypatch without importing ragas.
        """
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        metric_map = {
            "faithfulness": faithfulness,
            "context_precision": context_precision,
            "context_recall": context_recall,
            "answer_relevancy": answer_relevancy,
        }
        metric = metric_map[name]
        row: dict[str, Any] = {
            "question": question,
            "user_input": question,
            "answer": answer,
            "response": answer,
            "contexts": contexts,
            "retrieved_contexts": contexts,
            "ground_truth": reference,
            "reference": reference,
        }
        dataset = Dataset.from_list([row])
        result = evaluate(dataset, metrics=[metric])
        # ragas Result behaves like Mapping
        scores = dict(result) if not isinstance(result, dict) else result
        raw = scores.get(name)
        if raw is None:
            # Some versions key by metric name differently
            for key, val in scores.items():
                if name in str(key).lower():
                    raw = val
                    break
        if raw is None:
            return None
        return float(raw)
