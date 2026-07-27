"""Unit tests for Legal Knowledge Gate 1–3 core behaviors."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from payroll_copilot.application.dto.legal_knowledge import (
    ApproveProposalRequest,
    AuthorityLevel,
    ChangeClassification,
    LegalChangeProposal,
    ProposalStatus,
    RejectProposalRequest,
    SyncTrigger,
)
from payroll_copilot.application.services.legal_change_analyzer import LegalChangeAnalyzer
from payroll_copilot.application.services.legal_knowledge_sync import (
    LegalKnowledgeSyncService,
    content_hash,
    normalize_source_text,
)
from payroll_copilot.application.services.legal_proposal_service import LegalProposalService
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.application.services.legal_source_registry import LegalSourceRegistry
from payroll_copilot.application.services.ragas_adapter import RagasAdapter
from payroll_copilot.application.services.version_aware_legal_retriever import (
    HybridApprovedLaborLawSearch,
    VersionAwareLegalRetriever,
)
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore
from payroll_copilot.infrastructure.rag.numpy_vector_store import (
    NumpyLegalVectorStore,
    cosine_similarity,
)
from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta, RagEvalMetricValue


@pytest.fixture
def rules_dir(tmp_path: Path) -> Path:
    rules = tmp_path / "labor_law"
    rules.mkdir()
    payload = {
        "version": "2026.1.0",
        "effective_from": "2026-01-01",
        "rules": {
            "minimum_wage_hourly": {
                "id": "legal.minimum_wage",
                "description": {"en": "Hourly minimum wage", "he": "שכר מינימום"},
                "parameters": {"amount": 32.11},
                "legal_reference": {"en": "Minimum Wage Law"},
                "severity": "critical",
                "scope": "general",
            }
        },
    }
    (rules / "labor_law.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return rules


@pytest.fixture
def store(tmp_path: Path) -> LegalKnowledgeStore:
    return LegalKnowledgeStore(tmp_path / "legal_knowledge")


def test_catalog_seeds_and_closes_version(rules_dir: Path) -> None:
    catalog = LegalRuleVersionCatalog(rules_dir)
    seeded = catalog.ensure_seeded_from_yaml()
    assert any(v.rule_id == "legal.minimum_wage" and v.version == 1 for v in seeded)
    new = catalog.create_new_version(
        rule_id="legal.minimum_wage",
        rule_body={"id": "legal.minimum_wage", "parameters": {"amount": 33.0}},
        effective_date=date(2026, 7, 1),
        approved_by="tester",
        source_file="labor_law.yaml",
    )
    assert new.version == 2
    assert new.valid_from == "2026-07-01"
    prev = catalog.list_versions("legal.minimum_wage")[0]
    # first version should be closed
    v1 = next(v for v in catalog.list_versions("legal.minimum_wage") if v.version == 1)
    assert v1.valid_to == "2026-06-30"
    assert v1.status == "SUPERSEDED"
    assert catalog.select_as_of("legal.minimum_wage", date(2026, 6, 15)).version == 1
    assert catalog.select_as_of("legal.minimum_wage", date(2026, 7, 2)).version == 2


def test_invalid_effective_date_rejected(rules_dir: Path) -> None:
    catalog = LegalRuleVersionCatalog(rules_dir)
    catalog.ensure_seeded_from_yaml()
    with pytest.raises(ValueError):
        catalog.create_new_version(
            rule_id="legal.minimum_wage",
            rule_body={"id": "legal.minimum_wage"},
            effective_date=date(2025, 1, 1),
            approved_by="tester",
        )


def test_source_registry_no_invented_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "watch_x",
                        "provider": "unconfigured",
                        "source_type": "WATCHED_SOURCE",
                        "url": None,
                        "authority_level": "OFFICIAL",
                        "related_rule_ids": ["legal.minimum_wage"],
                        "enabled": False,
                    },
                    {
                        "source_id": "kolzchut_base",
                        "provider": "kol_zchut",
                        "source_type": "DISCOVERY_SOURCE",
                        "url": "https://www.kolzchut.org.il",
                        "authority_level": "SECONDARY_INTERPRETATION",
                        "related_rule_ids": [],
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    from payroll_copilot.infrastructure.config.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "kol_zchut_base_url", "https://www.kolzchut.org.il")
    reg = LegalSourceRegistry(registry_path)
    sources = reg.load()
    watch = next(s for s in sources if s.source_id == "watch_x")
    assert watch.url is None
    assert watch.coverage_status == "unconfigured"
    disc = next(s for s in sources if s.source_id == "kolzchut_base")
    assert disc.authority_level == AuthorityLevel.SECONDARY_INTERPRETATION
    assert disc.url == "https://www.kolzchut.org.il"


@pytest.mark.asyncio
async def test_hash_unchanged_skips_ai(store: LegalKnowledgeStore, rules_dir: Path, tmp_path: Path) -> None:
    class BoomAnalyzer(LegalChangeAnalyzer):
        async def analyze(self, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("AI should not be called on unchanged hash")

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "watch_mw",
                        "provider": "test",
                        "source_type": "WATCHED_SOURCE",
                        "url": "https://example.test/mw",
                        "authority_level": "OFFICIAL",
                        "related_rule_ids": ["legal.minimum_wage"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    text = normalize_source_text("Minimum wage stays 32.11")
    store.save_snapshot(source_id="watch_mw", content=text, content_hash=content_hash(text))
    service = LegalKnowledgeSyncService(
        registry=LegalSourceRegistry(registry_path),
        store=store,
        analyzer=BoomAnalyzer(),
        catalog=LegalRuleVersionCatalog(rules_dir),
        rules_path=str(rules_dir),
    )
    run = await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        content_overrides={"watch_mw": text},
    )
    assert run.unchanged_count == 1
    assert all(o.proposal_id is None for o in run.outcomes)


@pytest.mark.asyncio
async def test_material_change_creates_proposal(
    store: LegalKnowledgeStore, rules_dir: Path, tmp_path: Path
) -> None:
    class FakeAnalyzer(LegalChangeAnalyzer):
        async def analyze(self, **kwargs):  # type: ignore[no-untyped-def]
            from payroll_copilot.application.dto.legal_knowledge import LegalChangeAnalysis

            return LegalChangeAnalysis(
                classification=ChangeClassification.MATERIAL_CHANGE,
                affected_rule_ids=["legal.minimum_wage"],
                summary="Amount changed",
                reasoning_summary="Diff shows amount update",
                candidate_effective_date=None,
                confidence=0.7,
                requires_human_review=True,
                evidence_references=["diff"],
            )

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "watch_mw",
                        "provider": "test",
                        "source_type": "WATCHED_SOURCE",
                        "url": "https://example.test/mw",
                        "authority_level": "OFFICIAL",
                        "related_rule_ids": ["legal.minimum_wage"],
                        "enabled": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    old = "amount: 32.11"
    store.save_snapshot(source_id="watch_mw", content=old, content_hash=content_hash(old))
    service = LegalKnowledgeSyncService(
        registry=LegalSourceRegistry(registry_path),
        store=store,
        analyzer=FakeAnalyzer(),
        catalog=LegalRuleVersionCatalog(rules_dir),
        rules_path=str(rules_dir),
    )
    run = await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        content_overrides={"watch_mw": "amount: 40.00"},
    )
    assert run.material_change_count == 1
    proposals = store.list_proposals(status=ProposalStatus.PENDING_REVIEW)
    assert len(proposals) == 1
    assert proposals[0].requires_human_review is True


@pytest.mark.asyncio
async def test_partial_source_failure_continues(
    store: LegalKnowledgeStore, rules_dir: Path, tmp_path: Path
) -> None:
    class FakeAnalyzer(LegalChangeAnalyzer):
        async def analyze(self, **kwargs):  # type: ignore[no-untyped-def]
            from payroll_copilot.application.dto.legal_knowledge import LegalChangeAnalysis

            return LegalChangeAnalysis(
                classification=ChangeClassification.IRRELEVANT_CHANGE,
                summary="noise",
                reasoning_summary="noise",
                requires_human_review=False,
            )

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "bad",
                        "provider": "test",
                        "source_type": "WATCHED_SOURCE",
                        "url": "https://example.test/bad",
                        "authority_level": "OFFICIAL",
                        "related_rule_ids": [],
                        "enabled": True,
                    },
                    {
                        "source_id": "good",
                        "provider": "test",
                        "source_type": "WATCHED_SOURCE",
                        "url": "https://example.test/good",
                        "authority_level": "OFFICIAL",
                        "related_rule_ids": ["legal.minimum_wage"],
                        "enabled": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    service = LegalKnowledgeSyncService(
        registry=LegalSourceRegistry(registry_path),
        store=store,
        analyzer=FakeAnalyzer(),
        catalog=LegalRuleVersionCatalog(rules_dir),
        rules_path=str(rules_dir),
    )

    async def boom_fetch(url: str) -> str:
        if "bad" in url:
            raise RuntimeError("fetch failed")
        return "ok content"

    service._fetch = boom_fetch  # type: ignore[method-assign]
    run = await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        content_overrides={"good": "ok content changed"},
    )
    assert run.error_count >= 1
    assert run.sources_checked == 2
    assert run.status.value in {"COMPLETED_WITH_ERRORS", "COMPLETED"}


def test_analyzer_parse_and_failure() -> None:
    ok = LegalChangeAnalyzer.parse_structured(
        '{"classification":"MATERIAL_CHANGE","affected_rule_ids":["legal.minimum_wage"],'
        '"summary":"x","reasoning_summary":"y","candidate_effective_date":null,'
        '"confidence":0.5,"requires_human_review":true,"evidence_references":["d"]}',
        fallback_rule_ids=["legal.minimum_wage"],
    )
    assert ok.classification == ChangeClassification.MATERIAL_CHANGE
    bad = LegalChangeAnalyzer.parse_structured("not-json", fallback_rule_ids=["legal.minimum_wage"])
    assert bad.classification == ChangeClassification.UNCERTAIN


@pytest.mark.asyncio
async def test_approve_and_reject(store: LegalKnowledgeStore, rules_dir: Path) -> None:
    catalog = LegalRuleVersionCatalog(rules_dir)
    catalog.ensure_seeded_from_yaml()
    proposal = LegalChangeProposal(
        proposal_id=str(uuid4()),
        source_id="watch_mw",
        classification=ChangeClassification.MATERIAL_CHANGE,
        affected_rule_ids=["legal.minimum_wage"],
        status=ProposalStatus.PENDING_REVIEW,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        authority_level=AuthorityLevel.OFFICIAL,
        requires_human_review=True,
    )
    store.save_proposal(proposal)
    service = LegalProposalService(store=store, catalog=catalog, rules_path=str(rules_dir))
    user = uuid4()
    with pytest.raises(ValueError):
        await service.approve(
            proposal.proposal_id,
            ApproveProposalRequest(effective_date=date(2026, 8, 1), confirm_effective_date=False),
            reviewer_user_id=user,
        )
    approved = await service.approve(
        proposal.proposal_id,
        ApproveProposalRequest(effective_date=date(2026, 8, 1), confirm_effective_date=True),
        reviewer_user_id=user,
    )
    assert approved.status == ProposalStatus.APPROVED
    assert catalog.get_active("legal.minimum_wage").version == 2

    p2 = LegalChangeProposal(
        proposal_id=str(uuid4()),
        source_id="watch_mw",
        classification=ChangeClassification.MATERIAL_CHANGE,
        affected_rule_ids=["legal.minimum_wage"],
        status=ProposalStatus.PENDING_REVIEW,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        authority_level=AuthorityLevel.OFFICIAL,
    )
    store.save_proposal(p2)
    rejected = await service.reject(
        p2.proposal_id,
        RejectProposalRequest(reason="noise"),
        reviewer_user_id=user,
    )
    assert rejected.status == ProposalStatus.REJECTED
    assert catalog.get_active("legal.minimum_wage").version == 2


def test_cosine_and_effective_date_filter(store: LegalKnowledgeStore) -> None:
    vectors = NumpyLegalVectorStore(store)
    chunks = [
        IndexedChunkMeta(
            chunk_id="c1",
            rule_id="legal.minimum_wage",
            rule_version="1",
            valid_from=date(2024, 1, 1),
            valid_to=date(2025, 12, 31),
            approval_status="approved",
            text="old wage",
            content_hash="a",
        ),
        IndexedChunkMeta(
            chunk_id="c2",
            rule_id="legal.minimum_wage",
            rule_version="2",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            approval_status="approved",
            text="new wage",
            content_hash="b",
        ),
        IndexedChunkMeta(
            chunk_id="c3",
            rule_id="pending.rule",
            rule_version="1",
            valid_from=date(2026, 1, 1),
            approval_status="pending",
            text="should not retrieve",
            content_hash="c",
        ),
    ]
    embs = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.0]]
    vectors.upsert(chunks, embs, embedding_model="test")
    hits = vectors.search([1.0, 0.0], top_k=5, effective_date=date(2026, 6, 1))
    ids = [h[1]["chunk_id"] for h in hits]
    assert "c2" in ids
    assert "c1" not in ids
    assert "c3" not in ids
    assert cosine_similarity([1, 0], [1, 0]) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_hybrid_fallback_diagnostics(store: LegalKnowledgeStore, rules_dir: Path) -> None:
    retriever = VersionAwareLegalRetriever(model=None, store=store)
    hybrid = HybridApprovedLaborLawSearch(str(rules_dir), retriever=retriever)
    hits = await hybrid.asearch("minimum wage")
    assert hybrid.last_diagnostics.get("retrieval_mode") == "yaml_fallback"
    assert hits  # yaml should find something


def test_ragas_unavailable_never_zero() -> None:
    adapter = RagasAdapter(enabled=True)
    adapter._ragas_version = None
    adapter._import_error = "missing"
    scores = adapter.score_case(
        question="q",
        reference_answer="r",
        generated_answer="a",
        retrieved_contexts=["c"],
    )
    for metric in scores.values():
        assert metric.status == "unavailable"
        assert metric.value is None


def test_ragas_no_contexts_unavailable() -> None:
    adapter = RagasAdapter(enabled=False)
    scores = adapter.score_case(
        question="q",
        reference_answer="r",
        generated_answer="answer",
        retrieved_contexts=[],
    )
    assert scores["faithfulness"].status == "unavailable"
    assert scores["faithfulness"].value is None


def test_temporal_metric_helpers() -> None:
    from payroll_copilot.application.services.rag_evaluation import _temporal_check

    ok, detail = _temporal_check(
        expected_rules=["legal.minimum_wage"],
        hits=[
            {
                "rule_id": "legal.minimum_wage",
                "rule_version": "2",
                "valid_from": "2026-01-01",
                "valid_to": None,
            }
        ],
        effective_date=date(2026, 6, 1),
    )
    assert ok is True
    bad, _ = _temporal_check(
        expected_rules=["legal.minimum_wage"],
        hits=[
            {
                "rule_id": "legal.minimum_wage",
                "rule_version": "1",
                "valid_from": "2027-01-01",
                "valid_to": None,
            }
        ],
        effective_date=date(2026, 6, 1),
    )
    assert bad is False
