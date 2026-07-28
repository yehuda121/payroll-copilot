"""RAGAS adapter boundary — never fabricates scores; UNAVAILABLE on errors/missing evidence."""

from __future__ import annotations

import asyncio
import logging
import math
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from payroll_copilot.application.dto.legal_knowledge import RagEvalMetricValue

logger = logging.getLogger(__name__)

# Pinned conceptually; actual import verified at runtime.
RAGAS_VERSION_PIN = "0.2.15"

_NEST_ASYNCIO_UVLOOP_SAFE = False

T = TypeVar("T")


def _ensure_ragas_langchain_compat() -> None:
    """ragas 0.2 imports ChatVertexAI from langchain_community; 0.4+ removed that module."""
    key = "langchain_community.chat_models.vertexai"
    if key in sys.modules:
        return
    try:
        from langchain_google_vertexai import ChatVertexAI
    except Exception:  # noqa: BLE001

        class ChatVertexAI:  # type: ignore[no-redef]
            """Stub so ragas can import when VertexAI extras are absent."""

    mod = types.ModuleType(key)
    mod.ChatVertexAI = ChatVertexAI
    sys.modules[key] = mod
    try:
        import langchain_community.chat_models as chat_models

        if getattr(chat_models, "vertexai", None) is None:
            chat_models.vertexai = mod  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _ensure_nest_asyncio_uvloop_safe() -> None:
    """Prevent ragas' import-time nest_asyncio.apply() from failing under uvloop.

    uvicorn[standard] runs FastAPI on uvloop. ragas 0.2 calls nest_asyncio.apply()
    when executor.py is imported; nest_asyncio cannot patch uvloop and raises
    ValueError, which made Admin summary report RAGAS unavailable even though
    evaluation can succeed off the server loop.
    """
    global _NEST_ASYNCIO_UVLOOP_SAFE
    if _NEST_ASYNCIO_UVLOOP_SAFE:
        return
    try:
        import nest_asyncio
    except ImportError:
        _NEST_ASYNCIO_UVLOOP_SAFE = True
        return

    if getattr(nest_asyncio.apply, "_payroll_uvloop_safe", False):
        _NEST_ASYNCIO_UVLOOP_SAFE = True
        return

    original = nest_asyncio.apply

    def safe_apply(loop: Any = None) -> Any:
        target = loop
        if target is None:
            try:
                target = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    target = asyncio.get_event_loop()
                except RuntimeError:
                    target = None
        if target is not None:
            loop_type = type(target)
            if "uvloop" in loop_type.__module__.lower() or "uvloop" in loop_type.__name__.lower():
                logger.debug("nest_asyncio.apply skipped for %s", loop_type)
                return None
        try:
            return original(loop=loop)
        except ValueError as exc:
            if "patch loop" in str(exc).lower():
                logger.debug("nest_asyncio.apply skipped: %s", exc)
                return None
            raise

    safe_apply._payroll_uvloop_safe = True  # type: ignore[attr-defined]
    nest_asyncio.apply = safe_apply  # type: ignore[assignment]
    _NEST_ASYNCIO_UVLOOP_SAFE = True


def _call_in_standard_event_loop(fn: Callable[[], T]) -> T:
    """Run sync RAGAS work on a dedicated stdlib asyncio loop (never the server uvloop)."""

    def runner() -> T:
        # Force stdlib loops even if the process policy is uvloop (uvicorn[standard]).
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return fn()
        finally:
            try:
                loop.close()
            finally:
                asyncio.set_event_loop(None)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop (CLI / unit tests): run inline.
        return fn()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ragas-eval") as pool:
        return pool.submit(runner).result()


class RagasAdapter:
    """Thin adapter around RAGAS metrics. Unit tests mock this class."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._ragas_version: str | None = None
        self._import_error: str | None = None
        self._judge_llm: Any | None = None
        self._judge_embeddings: Any | None = None
        self._judge_config: dict[str, Any] | None = None
        self._judge_error: str | None = None
        if enabled:
            self._try_import()

    def _try_import(self) -> None:
        try:
            _ensure_nest_asyncio_uvloop_safe()
            _ensure_ragas_langchain_compat()
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

    @property
    def judge_config(self) -> dict[str, Any] | None:
        """Non-secret judge wiring used for baseline reproducibility."""
        if self._judge_config is None and self.available:
            try:
                self._ensure_judge()
            except Exception:  # noqa: BLE001
                pass
        return self._judge_config

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

        # RAGAS evaluate() nests event-loop work. Under FastAPI/uvloop that raises
        # "loop already running" / nest_asyncio errors — isolate on a stdlib loop.
        return _call_in_standard_event_loop(
            lambda: self._score_case_body(
                question=question,
                reference_answer=reference_answer,
                generated_answer=generated_answer,
                retrieved_contexts=retrieved_contexts,
            )
        )

    def _score_case_body(
        self,
        *,
        question: str,
        reference_answer: str,
        generated_answer: str,
        retrieved_contexts: list[str],
    ) -> dict[str, RagEvalMetricValue]:
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

        return self._safe_all_metrics(
            question=question,
            answer=generated_answer,
            contexts=retrieved_contexts,
            reference=reference_answer,
        )

    def _safe_all_metrics(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> dict[str, RagEvalMetricValue]:
        names = ("faithfulness", "context_precision", "context_recall", "answer_relevancy")
        try:
            values = self._compute_all(
                question=question,
                answer=answer,
                contexts=contexts,
                reference=reference,
            )
            out: dict[str, RagEvalMetricValue] = {}
            for name in names:
                raw = values.get(name)
                if raw is None:
                    out[name] = RagEvalMetricValue(
                        status="unavailable", reason=f"{name}_returned_none"
                    )
                else:
                    out[name] = RagEvalMetricValue(value=float(raw), status="ok")
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("ragas_metrics_batch_failed", extra={"error": str(exc)})
            # Fall back to per-metric so one failure does not blank the case.
            return {
                name: self._safe_metric(
                    name,
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    reference=reference,
                )
                for name in names
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

    def _ensure_judge(self) -> tuple[Any, Any]:
        if self._judge_llm is not None and self._judge_embeddings is not None:
            return self._judge_llm, self._judge_embeddings

        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper

        from payroll_copilot.infrastructure.config.settings import get_settings

        settings = get_settings()
        openai_key = (settings.openai_api_key or "").strip()
        if openai_key:
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings

            # Prefer a lightweight judge model; "gpt-5" may not be available for eval.
            judge_model = (settings.openai_model or "gpt-4o-mini").strip()
            if judge_model.lower() in {"gpt-5", "gpt-5.0"}:
                judge_model = "gpt-4o-mini"
            emb_model = (settings.openai_embedding_model or "text-embedding-3-small").strip()
            llm = LangchainLLMWrapper(
                ChatOpenAI(api_key=openai_key, model=judge_model, temperature=0)
            )
            embeddings = LangchainEmbeddingsWrapper(
                OpenAIEmbeddings(api_key=openai_key, model=emb_model)
            )
            self._judge_config = {
                "judge_provider": "openai",
                "judge_llm_model": judge_model,
                "judge_embedding_model": emb_model,
            }
            self._judge_llm = llm
            self._judge_embeddings = embeddings
            return llm, embeddings

        # Local fallback: same Ollama stack as retrieval/answer generation.
        from langchain_ollama import ChatOllama, OllamaEmbeddings

        base_url = (
            (getattr(settings, "ollama_base_url", None) or "").strip()
            or (getattr(settings, "ollama_local_url", None) or "").strip()
            or "http://127.0.0.1:11434"
        )
        chat_model = (getattr(settings, "ollama_default_model", None) or "mistral-nemo:12b").strip()
        emb_model = (getattr(settings, "ollama_embedding_model", None) or "nomic-embed-text").strip()
        llm = LangchainLLMWrapper(ChatOllama(model=chat_model, base_url=base_url, temperature=0))
        embeddings = LangchainEmbeddingsWrapper(
            OllamaEmbeddings(model=emb_model, base_url=base_url)
        )
        self._judge_config = {
            "judge_provider": "ollama",
            "judge_llm_model": chat_model,
            "judge_embedding_model": emb_model,
            "judge_base_url": base_url,
        }
        self._judge_llm = llm
        self._judge_embeddings = embeddings
        return llm, embeddings

    def _extract_scores(self, result: Any, names: tuple[str, ...]) -> dict[str, float | None]:
        out: dict[str, float | None] = {n: None for n in names}
        scores_attr = getattr(result, "scores", None)
        row: dict[str, Any] = {}
        if isinstance(scores_attr, list) and scores_attr and isinstance(scores_attr[0], dict):
            row = scores_attr[0]
        elif isinstance(result, dict):
            row = result
        else:
            try:
                row = dict(result)
            except Exception:  # noqa: BLE001
                row = {}
            if not row:
                try:
                    frame = result.to_pandas()
                    if len(frame):
                        row = {col: frame[col].iloc[0] for col in frame.columns}
                except Exception:  # noqa: BLE001
                    row = {}

        for name in names:
            raw = row.get(name)
            if raw is None:
                for key, val in row.items():
                    if name in str(key).lower():
                        raw = val
                        break
            if raw is None:
                out[name] = None
            else:
                try:
                    value = float(raw)
                    if math.isnan(value):
                        out[name] = None
                    else:
                        out[name] = value
                except (TypeError, ValueError):
                    out[name] = None
        return out

    def _compute_all(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> dict[str, float | None]:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        llm, embeddings = self._ensure_judge()
        names = ("faithfulness", "context_precision", "context_recall", "answer_relevancy")
        metric_objs = [faithfulness, context_precision, context_recall, answer_relevancy]
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
        result = evaluate(dataset, metrics=metric_objs, llm=llm, embeddings=embeddings)
        return self._extract_scores(result, names)

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

        llm, embeddings = self._ensure_judge()
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
        result = evaluate(dataset, metrics=[metric], llm=llm, embeddings=embeddings)
        return self._extract_scores(result, (name,)).get(name)
