"""Local multilingual cross-encoder legal chunk reranker (BGE v2-m3)."""

from __future__ import annotations

import logging
import math
import threading
from typing import Any, Sequence

from payroll_copilot.application.ports.legal_chunk_reranker import LegalRerankCandidate

logger = logging.getLogger(__name__)

DEFAULT_LEGAL_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

# Process-local singleton cache: model_id -> CrossEncoder (or load error marker).
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()
_LOAD_ERRORS: dict[str, str] = {}


class CrossEncoderLegalChunkReranker:
    """Scores authorized candidates with a local multilingual cross-encoder.

    Does not retrieve or invent chunks. Metadata is preserved by the Phase 2
    sanitizer; this adapter only reorders by descending relevance score.
    """

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_LEGAL_RERANK_MODEL,
        device: str | None = None,
        max_length: int = 512,
        batch_size: int = 8,
    ) -> None:
        self._model_id = (model_id or DEFAULT_LEGAL_RERANK_MODEL).strip() or DEFAULT_LEGAL_RERANK_MODEL
        self._device = device  # None → sentence-transformers auto (cpu/cuda)
        self._max_length = max(64, int(max_length))
        self._batch_size = max(1, int(batch_size))

    @property
    def model_id(self) -> str:
        return self._model_id

    def ensure_loaded(self) -> None:
        """Lazy-load and cache the cross-encoder once per process."""
        if self._model_id in _MODEL_CACHE:
            return
        if self._model_id in _LOAD_ERRORS:
            raise RuntimeError(_LOAD_ERRORS[self._model_id])

        with _MODEL_LOCK:
            if self._model_id in _MODEL_CACHE:
                return
            if self._model_id in _LOAD_ERRORS:
                raise RuntimeError(_LOAD_ERRORS[self._model_id])
            try:
                from sentence_transformers import CrossEncoder
            except Exception as exc:  # noqa: BLE001
                msg = (
                    f"sentence_transformers_unavailable:{type(exc).__name__}:{exc}. "
                    "Install optional extra: pip install 'payroll-copilot[legal-rerank]'"
                )
                _LOAD_ERRORS[self._model_id] = msg
                raise RuntimeError(msg) from exc

            try:
                kwargs: dict[str, Any] = {"max_length": self._max_length}
                if self._device:
                    kwargs["device"] = self._device
                model = CrossEncoder(self._model_id, **kwargs)
                _MODEL_CACHE[self._model_id] = model
                logger.info(
                    "legal_rerank_model_loaded",
                    extra={"model_id": self._model_id, "device": self._device or "auto"},
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"legal_rerank_model_load_failed:{type(exc).__name__}:{exc}"
                _LOAD_ERRORS[self._model_id] = msg
                logger.exception("legal_rerank_model_load_failed", extra={"model_id": self._model_id})
                raise RuntimeError(msg) from exc

    def _model(self) -> Any:
        self.ensure_loaded()
        return _MODEL_CACHE[self._model_id]

    def rerank(
        self,
        query: str,
        candidates: Sequence[LegalRerankCandidate],
    ) -> Sequence[LegalRerankCandidate]:
        if not candidates:
            return []
        q = (query or "").strip()
        if not q:
            raise ValueError("rerank_query_empty")

        pairs: list[list[str]] = []
        for row in candidates:
            text = str(row.get("text") or row.get("title") or "").strip()
            if not text:
                text = str(row.get("rule_id") or row.get("chunk_id") or "")
            pairs.append([q, text])

        model = self._model()
        raw_scores = model.predict(
            pairs,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        scores = _coerce_scores(raw_scores, expected=len(candidates))
        ranked = sorted(
            zip(range(len(candidates)), scores, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        # Return shallow copies with optional diagnostic score; sanitizer restores metadata.
        out: list[dict[str, Any]] = []
        for idx, score in ranked:
            row = dict(candidates[idx])
            row["rerank_score"] = float(score)
            out.append(row)
        return out


def _coerce_scores(raw: Any, *, expected: int) -> list[float]:
    try:
        values = list(raw)
    except TypeError as exc:
        raise ValueError("rerank_scores_not_iterable") from exc
    if len(values) != expected:
        raise ValueError(f"rerank_score_count_mismatch:{len(values)}!={expected}")
    out: list[float] = []
    for item in values:
        try:
            score = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError("rerank_score_non_numeric") from exc
        if math.isnan(score) or math.isinf(score):
            raise ValueError("rerank_score_non_finite")
        out.append(score)
    return out


def reset_legal_rerank_model_cache() -> None:
    """Test helper — clears process-local model cache."""
    with _MODEL_LOCK:
        _MODEL_CACHE.clear()
        _LOAD_ERRORS.clear()
