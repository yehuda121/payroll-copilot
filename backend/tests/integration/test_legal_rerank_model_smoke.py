"""Optional real-model smoke for legal reranker (downloads weights; not CI-default).

Run:
  py -3 -m pytest tests/integration/test_legal_rerank_model_smoke.py -m real_model -q
"""

from __future__ import annotations

import pytest

from payroll_copilot.application.services.legal_chunk_reranker import apply_rerank_fail_open
from payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker import (
    CrossEncoderLegalChunkReranker,
    reset_legal_rerank_model_cache,
)
from payroll_copilot.infrastructure.rag.legal_reranker_factory import build_legal_chunk_reranker


pytestmark = pytest.mark.real_model


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_legal_rerank_model_cache()
    yield
    reset_legal_rerank_model_cache()


def _candidates() -> list[dict]:
    return [
        {
            "chunk_id": "mw",
            "rule_id": "legal.minimum_wage",
            "text": "שכר המינימום החודשי לעובד במשרה מלאה נקבע בחוק ומתעדכן מעת לעת.",
        },
        {
            "chunk_id": "ot",
            "rule_id": "legal.overtime.daily_limit",
            "text": "משך שעות העבודה היומיות מוגבל; שעות נוספות מעבר למכסה מחייבות תשלום מוגדל.",
        },
        {
            "chunk_id": "vac",
            "rule_id": "legal.vacation.annual_entitlement",
            "text": "עובד זכאי לימי חופשה שנתיים בהתאם לוותק ולחוק חופשה שנתית.",
        },
        {
            "chunk_id": "pen",
            "rule_id": "legal.pension.contribution",
            "text": "שיעורי הפרשות פנסיה חובה של עובד ומעסיק נקבעים בצו ההרחבה.",
        },
    ]


@pytest.mark.integration
def test_english_query_prefers_hebrew_minimum_wage_chunk() -> None:
    pytest.importorskip("sentence_transformers")
    reranker = CrossEncoderLegalChunkReranker(device="cpu")
    hits, diag = apply_rerank_fail_open(
        query="What is the current monthly minimum wage?",
        candidates=_candidates(),
        reranker=reranker,
        final_n=4,
    )
    assert diag["rerank_fallback"] is False
    assert hits[0]["chunk_id"] == "mw"
    assert diag["order_changed"] is True or hits[0]["chunk_id"] == "mw"


@pytest.mark.integration
def test_hebrew_query_prefers_overtime_chunk() -> None:
    pytest.importorskip("sentence_transformers")
    reranker = CrossEncoderLegalChunkReranker(device="cpu")
    hits, diag = apply_rerank_fail_open(
        query="מה מגבלת שעות נוספות ביום?",
        candidates=_candidates(),
        reranker=reranker,
        final_n=4,
    )
    assert diag["rerank_fallback"] is False
    assert hits[0]["chunk_id"] == "ot"


@pytest.mark.integration
def test_factory_fail_open_path_with_real_wrapper() -> None:
    pytest.importorskip("sentence_transformers")
    from types import SimpleNamespace

    settings = SimpleNamespace(
        legal_rag_rerank_enabled=True,
        legal_rag_rerank_model="BAAI/bge-reranker-v2-m3",
        legal_rag_rerank_timeout_ms=120_000,
        legal_rag_rerank_device="cpu",
    )
    wrapped = build_legal_chunk_reranker(settings)
    assert wrapped is not None
    hits, diag = apply_rerank_fail_open(
        query="pension employee contribution rate",
        candidates=_candidates(),
        reranker=wrapped,
        final_n=2,
    )
    assert diag["rerank_fallback"] is False
    assert hits[0]["chunk_id"] == "pen"
    assert len(hits) == 2
