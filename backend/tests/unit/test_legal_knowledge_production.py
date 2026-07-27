"""Production-completion tests: SSRF, sync E2E fixtures, chroma persistence, auth."""

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
    IndexedChunkMeta,
    LegalChangeProposal,
    ProposalStatus,
    RejectProposalRequest,
    SyncTrigger,
)
from payroll_copilot.application.services.legal_change_analyzer import LegalChangeAnalyzer
from payroll_copilot.application.services.legal_knowledge_sync import LegalKnowledgeSyncService
from payroll_copilot.application.services.legal_proposal_service import LegalProposalService
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.application.services.legal_source_registry import LegalSourceRegistry
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore
from payroll_copilot.infrastructure.rag.chroma_vector_store import ChromaLegalVectorStore
from payroll_copilot.infrastructure.security.safe_url import (
    UnsafeSourceUrlError,
    assert_safe_public_https_url,
)


def test_ssrf_blocks_localhost_and_private(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(UnsafeSourceUrlError):
        assert_safe_public_https_url("http://example.com")
    with pytest.raises(UnsafeSourceUrlError):
        assert_safe_public_https_url("https://localhost/secret")
    with pytest.raises(UnsafeSourceUrlError):
        assert_safe_public_https_url("https://127.0.0.1/")
    with pytest.raises(UnsafeSourceUrlError):
        assert_safe_public_https_url("https://192.168.1.1/")
    with pytest.raises(UnsafeSourceUrlError):
        assert_safe_public_https_url("https://evil.example/", allow_hosts={"www.kolzchut.org.il"})

    import payroll_copilot.infrastructure.security.safe_url as safe_url

    monkeypatch.setattr(safe_url, "_assert_public_host", lambda host: None)
    ok = assert_safe_public_https_url(
        "https://www.kolzchut.org.il/",
        allow_hosts={"www.kolzchut.org.il"},
    )
    assert "kolzchut" in ok


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
                "description": {"en": "Hourly minimum wage"},
                "parameters": {"amount": 32.11},
                "legal_reference": {"en": "Minimum Wage Law"},
                "severity": "critical",
            }
        },
    }
    (rules / "labor_law.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    return rules


@pytest.mark.asyncio
async def test_sync_cases_a_b_c_d_e(tmp_path: Path, rules_dir: Path) -> None:
    store = LegalKnowledgeStore(tmp_path / "lk")
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

    class ScriptedAnalyzer(LegalChangeAnalyzer):
        def __init__(self) -> None:
            super().__init__(None)
            self.calls = 0
            self._queue = [
                ChangeClassification.IRRELEVANT_CHANGE,
                ChangeClassification.MATERIAL_CHANGE,
            ]

        async def analyze(self, **kwargs):  # type: ignore[no-untyped-def]
            from payroll_copilot.application.dto.legal_knowledge import LegalChangeAnalysis

            self.calls += 1
            classification = self._queue.pop(0) if self._queue else ChangeClassification.UNCERTAIN
            return LegalChangeAnalysis(
                classification=classification,
                affected_rule_ids=["legal.minimum_wage"],
                summary=classification.value,
                reasoning_summary="fixture",
                requires_human_review=True,
            )

    analyzer = ScriptedAnalyzer()
    service = LegalKnowledgeSyncService(
        registry=LegalSourceRegistry(registry_path),
        store=store,
        analyzer=analyzer,
        catalog=LegalRuleVersionCatalog(rules_dir),
        rules_path=str(rules_dir),
    )

    # CASE A — unchanged
    text_a = "amount remains 32.11"
    from payroll_copilot.application.services.legal_knowledge_sync import content_hash, normalize_source_text

    norm = normalize_source_text(text_a)
    store.save_snapshot(source_id="watch_mw", content=norm, content_hash=content_hash(norm))
    run_a = await service.run_sync(
        trigger=SyncTrigger.MANUAL, content_overrides={"watch_mw": text_a}
    )
    assert run_a.unchanged_count == 1
    assert analyzer.calls == 0

    # CASE B — irrelevant change (non-HTML text so normalization preserves the delta)
    run_b = await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        content_overrides={"watch_mw": text_a + "\nUpdated page chrome and navigation labels only."},
    )
    assert run_b.irrelevant_change_count == 1
    assert analyzer.calls == 1
    assert store.list_proposals(status=ProposalStatus.PENDING_REVIEW) == []

    # CASE C — material → proposal, no version bump yet
    catalog = LegalRuleVersionCatalog(rules_dir)
    catalog.ensure_seeded_from_yaml()
    before = catalog.get_active("legal.minimum_wage")
    run_c = await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        content_overrides={"watch_mw": "amount changed to 40.00 legally"},
    )
    assert run_c.material_change_count == 1
    proposals = store.list_proposals(status=ProposalStatus.PENDING_REVIEW)
    assert len(proposals) == 1
    assert catalog.get_active("legal.minimum_wage").version == before.version

    # CASE D — approve
    proposal_svc = LegalProposalService(
        store=store, catalog=catalog, rules_path=str(rules_dir)
    )
    user = uuid4()
    approved = await proposal_svc.approve(
        proposals[0].proposal_id,
        ApproveProposalRequest(effective_date=date(2026, 9, 1), confirm_effective_date=True),
        reviewer_user_id=user,
    )
    assert approved.status == ProposalStatus.APPROVED
    assert catalog.get_active("legal.minimum_wage").version == before.version + 1
    v_prev = next(v for v in catalog.list_versions("legal.minimum_wage") if v.version == before.version)
    assert v_prev.valid_to == "2026-08-31"

    # CASE E — reject another proposal
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
    rejected = await proposal_svc.reject(
        p2.proposal_id, RejectProposalRequest(reason="noise"), reviewer_user_id=user
    )
    assert rejected.status == ProposalStatus.REJECTED
    assert catalog.get_active("legal.minimum_wage").version == before.version + 1


def test_chroma_persists_across_instances(tmp_path: Path) -> None:
    pytest.importorskip("chromadb")
    path = tmp_path / "chroma"
    store1 = ChromaLegalVectorStore(persist_path=path, collection_name="test_legal_v1")
    chunks = [
        IndexedChunkMeta(
            chunk_id="c1",
            rule_id="legal.minimum_wage",
            rule_version="1",
            valid_from=date(2024, 1, 1),
            valid_to=date(2025, 12, 31),
            approval_status="approved",
            text="old minimum wage",
            content_hash="a",
            scope="general",
        ),
        IndexedChunkMeta(
            chunk_id="c2",
            rule_id="legal.minimum_wage",
            rule_version="2",
            valid_from=date(2026, 1, 1),
            valid_to=None,
            approval_status="approved",
            text="new minimum wage",
            content_hash="b",
            scope="general",
        ),
        IndexedChunkMeta(
            chunk_id="pending",
            rule_id="pending.rule",
            rule_version="1",
            valid_from=date(2026, 1, 1),
            approval_status="pending",
            text="should not retrieve",
            content_hash="c",
        ),
    ]
    embs = [[1.0, 0.0, 0.0], [0.95, 0.05, 0.0], [1.0, 0.0, 0.0]]
    store1.upsert(chunks, embs, embedding_model="test-embed")
    assert store1.count() == 3

    # New instance = restart simulation
    store2 = ChromaLegalVectorStore(persist_path=path, collection_name="test_legal_v1")
    assert store2.count() == 3
    hits = store2.search([1.0, 0.0, 0.0], top_k=5, effective_date=date(2026, 6, 1))
    ids = [h[1]["chunk_id"] for h in hits]
    assert "c2" in ids
    assert "c1" not in ids
    assert "pending" not in ids
    hist = store2.search([1.0, 0.0, 0.0], top_k=5, effective_date=date(2025, 6, 1))
    hist_ids = [h[1]["chunk_id"] for h in hist]
    assert "c1" in hist_ids
    assert "c2" not in hist_ids


def test_benchmark_case_count() -> None:
    path = Path(__file__).resolve().parents[2] / "config" / "rag_eval" / "benchmark_v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    enabled = [c for c in data["cases"] if c.get("enabled", True)]
    assert len(enabled) >= 20
    assert data["dataset_version"] == "benchmark_v1"
