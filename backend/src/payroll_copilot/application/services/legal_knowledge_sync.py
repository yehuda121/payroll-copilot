"""Central Legal Knowledge Sync — manual and scheduled share this service.

Never approves proposals or activates legal versions.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from difflib import unified_diff
from typing import Any
from uuid import uuid4

import httpx

from payroll_copilot.application.dto.legal_knowledge import (
    AuthorityLevel,
    ChangeClassification,
    LegalChangeProposal,
    LegalSyncRun,
    ProposalStatus,
    SourceSyncOutcome,
    SourceType,
    SyncRunStatus,
    SyncTrigger,
)
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.services.legal_change_analyzer import LegalChangeAnalyzer
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.application.services.legal_source_registry import LegalSourceRegistry
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

logger = logging.getLogger(__name__)


def normalize_source_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Strip common script/style blocks if HTML-ish
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LegalKnowledgeSyncService:
    def __init__(
        self,
        *,
        registry: LegalSourceRegistry | None = None,
        store: LegalKnowledgeStore | None = None,
        analyzer: LegalChangeAnalyzer | None = None,
        catalog: LegalRuleVersionCatalog | None = None,
        rules_path: str | None = None,
        audit: AuditLogRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        from payroll_copilot.infrastructure.config.settings import get_settings

        settings = get_settings()
        self._registry = registry or LegalSourceRegistry()
        self._store = store or LegalKnowledgeStore()
        self._analyzer = analyzer or LegalChangeAnalyzer()
        self._rules_path = rules_path or settings.legal_rules_path
        self._catalog = catalog or LegalRuleVersionCatalog(self._rules_path)
        self._audit = audit
        self._http = http_client

    async def run_sync(
        self,
        *,
        trigger: SyncTrigger,
        triggered_by: str | None = None,
        content_overrides: dict[str, str] | None = None,
    ) -> LegalSyncRun:
        run = LegalSyncRun(
            run_id=str(uuid4()),
            trigger=trigger,
            started_at=datetime.now(timezone.utc),
            status=SyncRunStatus.RUNNING,
            triggered_by=triggered_by,
        )
        self._store.save_sync_run(run)
        overrides = content_overrides or {}

        sources = self._registry.load()
        for source in sources:
            try:
                outcome = await self._sync_one_source(
                    run_id=run.run_id,
                    source_id=source.source_id,
                    source_type=source.source_type,
                    url=source.url,
                    enabled=source.enabled,
                    related_rule_ids=source.related_rule_ids,
                    authority_level=source.authority_level,
                    override_content=overrides.get(source.source_id),
                )
            except Exception as exc:  # noqa: BLE001 — isolate source failures
                logger.exception("legal_sync_source_failed", extra={"source_id": source.source_id})
                outcome = SourceSyncOutcome(
                    source_id=source.source_id,
                    classification=ChangeClassification.ERROR,
                    message="Source sync failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            run.outcomes.append(outcome)
            run.sources_checked += 1
            self._tally(run, outcome.classification)

        run.completed_at = datetime.now(timezone.utc)
        if run.error_count and (
            run.material_change_count
            or run.new_relevant_count
            or run.unchanged_count
            or run.irrelevant_change_count
            or run.uncertain_count
            or run.skipped_unconfigured_count
        ):
            run.status = SyncRunStatus.COMPLETED_WITH_ERRORS
        elif run.error_count and run.sources_checked == run.error_count:
            run.status = SyncRunStatus.FAILED
        else:
            run.status = SyncRunStatus.COMPLETED
        self._store.save_sync_run(run)

        if self._audit:
            await self._audit.append(
                AuditLogEntry(
                    action="legal_sync.completed",
                    resource_type="legal_sync_run",
                    resource_id=None,
                    organization_id=None,
                    user_id=None,
                    details={
                        "run_id": run.run_id,
                        "trigger": trigger.value,
                        "status": run.status.value,
                        "sources_checked": run.sources_checked,
                        "material_change_count": run.material_change_count,
                        "new_relevant_count": run.new_relevant_count,
                        "error_count": run.error_count,
                        "triggered_by": triggered_by,
                    },
                )
            )
        return run

    async def _sync_one_source(
        self,
        *,
        run_id: str,
        source_id: str,
        source_type: SourceType,
        url: str | None,
        enabled: bool,
        related_rule_ids: list[str],
        authority_level: str,
        override_content: str | None,
    ) -> SourceSyncOutcome:
        if not url and override_content is None:
            return SourceSyncOutcome(
                source_id=source_id,
                classification=ChangeClassification.SKIPPED_UNCONFIGURED,
                message="Source URL not configured; skipped. No invented URL used.",
            )
        if not enabled and override_content is None:
            return SourceSyncOutcome(
                source_id=source_id,
                classification=ChangeClassification.SKIPPED_UNCONFIGURED,
                message="Source disabled.",
            )

        if override_content is not None:
            raw = override_content
        else:
            raw = await self._fetch(url or "")

        normalized = normalize_source_text(raw)
        new_hash = content_hash(normalized)
        prior = self._store.get_source_state(source_id)
        old_hash = prior.get("last_content_hash")

        if old_hash and old_hash == new_hash:
            return SourceSyncOutcome(
                source_id=source_id,
                classification=ChangeClassification.NO_CHANGE,
                message="Content hash unchanged; AI analysis skipped.",
                content_hash=new_hash,
            )

        old_text = ""
        if prior.get("last_snapshot_id"):
            old_text = self._store.read_snapshot(str(prior["last_snapshot_id"])) or ""

        if source_type == SourceType.DISCOVERY_SOURCE:
            return await self._handle_discovery(
                run_id=run_id,
                source_id=source_id,
                url=url,
                authority_level=authority_level,
                normalized=normalized,
                new_hash=new_hash,
                old_text=old_text,
            )

        diff_text = "\n".join(
            unified_diff(
                old_text.splitlines(),
                normalized.splitlines(),
                fromfile="previous",
                tofile="current",
                lineterm="",
            )
        )[:12000]

        rule_context = self._rule_context(related_rule_ids)
        analysis = await self._analyzer.analyze(
            previous_text=old_text,
            new_text=normalized,
            diff_text=diff_text,
            related_rule_ids=related_rule_ids,
            current_rule_context=rule_context,
            source_metadata={
                "source_id": source_id,
                "url": url,
                "authority_level": authority_level,
                "related_rule_ids": related_rule_ids,
            },
        )

        snap_id = self._store.save_snapshot(source_id=source_id, content=normalized, content_hash=new_hash)
        proposal_id = None
        creates_proposal = analysis.classification in {
            ChangeClassification.MATERIAL_CHANGE,
            ChangeClassification.NEW_RELEVANT_LAW,
            ChangeClassification.UNCERTAIN,
            ChangeClassification.SOURCE_REMOVED,
        }
        if creates_proposal:
            proposal = LegalChangeProposal(
                proposal_id=str(uuid4()),
                source_id=source_id,
                classification=analysis.classification,
                affected_rule_ids=analysis.affected_rule_ids or related_rule_ids,
                old_snapshot_ref=str(prior.get("last_snapshot_id") or "") or None,
                new_snapshot_ref=snap_id,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                diff_text=diff_text,
                ai_summary=analysis.summary,
                reasoning_summary=analysis.reasoning_summary,
                candidate_effective_date=analysis.candidate_effective_date,
                confidence=analysis.confidence,
                requires_human_review=True,
                evidence_references=analysis.evidence_references,
                status=ProposalStatus.PENDING_REVIEW,
                created_at=datetime.now(timezone.utc),
                authority_level=(
                    authority_level
                    if isinstance(authority_level, AuthorityLevel)
                    else AuthorityLevel(str(authority_level))
                ),
                source_url=url,
                sync_run_id=run_id,
            )
            self._store.save_proposal(proposal)
            proposal_id = proposal.proposal_id
            if self._audit:
                await self._audit.append(
                    AuditLogEntry(
                        action="legal_sync.proposal_created",
                        resource_type="legal_change_proposal",
                        resource_id=None,
                        organization_id=None,
                        user_id=None,
                        details={
                            "proposal_id": proposal_id,
                            "source_id": source_id,
                            "classification": analysis.classification.value,
                            "affected_rule_ids": proposal.affected_rule_ids,
                            "new_content_hash": new_hash,
                            "sync_run_id": run_id,
                        },
                    )
                )

        return SourceSyncOutcome(
            source_id=source_id,
            classification=analysis.classification,
            message=analysis.summary or analysis.classification.value,
            proposal_id=proposal_id,
            content_hash=new_hash,
        )

    async def _handle_discovery(
        self,
        *,
        run_id: str,
        source_id: str,
        url: str | None,
        authority_level: str,
        normalized: str,
        new_hash: str,
        old_text: str,
    ) -> SourceSyncOutcome:
        item_key = f"{source_id}:{new_hash[:32]}"
        if self._store.discovery_seen(item_key, new_hash):
            self._store.save_snapshot(source_id=source_id, content=normalized, content_hash=new_hash)
            return SourceSyncOutcome(
                source_id=source_id,
                classification=ChangeClassification.NO_CHANGE,
                message="Discovery item already seen with same hash.",
                content_hash=new_hash,
            )

        diff_text = "\n".join(
            unified_diff(
                old_text.splitlines()[:200],
                normalized.splitlines()[:200],
                fromfile="previous",
                tofile="current",
                lineterm="",
            )
        )[:8000]

        analysis = await self._analyzer.analyze(
            previous_text=old_text[:8000],
            new_text=normalized[:8000],
            diff_text=diff_text,
            related_rule_ids=[],
            current_rule_context="Discovery source — classify relevance to Israeli payroll labor law only.",
            source_metadata={"source_id": source_id, "url": url, "authority_level": authority_level},
        )

        snap_id = self._store.save_snapshot(source_id=source_id, content=normalized, content_hash=new_hash)
        self._store.remember_discovery_item(item_key, new_hash)

        proposal_id = None
        if analysis.classification in {
            ChangeClassification.NEW_RELEVANT_LAW,
            ChangeClassification.MATERIAL_CHANGE,
            ChangeClassification.UNCERTAIN,
        }:
            # Force discovery proposals into NEW_RELEVANT_LAW when AI says material/new
            classification = (
                ChangeClassification.NEW_RELEVANT_LAW
                if analysis.classification != ChangeClassification.UNCERTAIN
                else ChangeClassification.UNCERTAIN
            )
            proposal = LegalChangeProposal(
                proposal_id=str(uuid4()),
                source_id=source_id,
                classification=classification,
                affected_rule_ids=[],
                old_snapshot_ref=None,
                new_snapshot_ref=snap_id,
                old_content_hash=None,
                new_content_hash=new_hash,
                diff_text=diff_text,
                ai_summary=analysis.summary,
                reasoning_summary=analysis.reasoning_summary,
                candidate_effective_date=analysis.candidate_effective_date,
                confidence=analysis.confidence,
                requires_human_review=True,
                evidence_references=analysis.evidence_references,
                status=ProposalStatus.PENDING_REVIEW,
                created_at=datetime.now(timezone.utc),
                authority_level=(
                    authority_level
                    if isinstance(authority_level, AuthorityLevel)
                    else AuthorityLevel(str(authority_level))
                ),
                source_url=url,
                sync_run_id=run_id,
            )
            self._store.save_proposal(proposal)
            proposal_id = proposal.proposal_id
        elif analysis.classification == ChangeClassification.IRRELEVANT_CHANGE:
            # remembered above — avoid re-surfacing
            pass

        return SourceSyncOutcome(
            source_id=source_id,
            classification=analysis.classification,
            message=analysis.summary or analysis.classification.value,
            proposal_id=proposal_id,
            content_hash=new_hash,
        )

    async def _fetch(self, url: str) -> str:
        from payroll_copilot.infrastructure.config.settings import get_settings
        from payroll_copilot.infrastructure.security.safe_url import (
            UnsafeSourceUrlError,
            assert_safe_public_https_url,
        )

        settings = get_settings()
        allowed_hosts: set[str] = set()
        for source in self._registry.load():
            if source.url:
                from urllib.parse import urlparse

                host = urlparse(source.url).hostname
                if host:
                    allowed_hosts.add(host.lower())
        try:
            safe_url = assert_safe_public_https_url(url, allow_hosts=allowed_hosts or None)
        except UnsafeSourceUrlError as exc:
            raise ValueError(f"unsafe_source_url:{exc}") from exc

        timeout = float(getattr(settings, "legal_fetch_timeout_seconds", 30.0))
        max_bytes = int(getattr(settings, "legal_fetch_max_bytes", 2_000_000))

        async def _read(client: httpx.AsyncClient) -> str:
            async with client.stream("GET", safe_url, follow_redirects=False) as response:
                # Manual redirect handling — re-validate each hop.
                hops = 0
                while response.is_redirect and hops < 3:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("redirect_without_location")
                    from urllib.parse import urljoin

                    next_url = urljoin(str(response.url), location)
                    safe_next = assert_safe_public_https_url(next_url, allow_hosts=allowed_hosts or None)
                    hops += 1
                    response = await client.send(
                        client.build_request("GET", safe_next),
                        stream=True,
                        follow_redirects=False,
                    )
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("source_content_too_large")
                    chunks.append(chunk)
                return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

        if self._http is not None:
            # Test client — still validate URL first.
            response = await self._http.get(safe_url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            text = response.text
            if len(text.encode("utf-8")) > max_bytes:
                raise ValueError("source_content_too_large")
            return text
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await _read(client)

    def _rule_context(self, rule_ids: list[str]) -> str:
        self._catalog.ensure_seeded_from_yaml()
        loader = YamlLegalRulesLoader(self._rules_path)
        bundle = loader.load_merged_rules()
        lines: list[str] = []
        for rule_id in rule_ids:
            for key, rule in bundle.rules.items():
                if rule.rule_id == rule_id or key == rule_id:
                    active = self._catalog.get_active(rule.rule_id)
                    lines.append(
                        f"rule_id={rule.rule_id} version={active.version if active else 'UNKNOWN'} "
                        f"params={rule.parameters}"
                    )
        return "\n".join(lines) or "No matching internal rules."

    @staticmethod
    def _tally(run: LegalSyncRun, classification: ChangeClassification) -> None:
        if classification == ChangeClassification.NO_CHANGE:
            run.unchanged_count += 1
        elif classification == ChangeClassification.IRRELEVANT_CHANGE:
            run.irrelevant_change_count += 1
        elif classification == ChangeClassification.MATERIAL_CHANGE:
            run.material_change_count += 1
        elif classification == ChangeClassification.NEW_RELEVANT_LAW:
            run.new_relevant_count += 1
        elif classification == ChangeClassification.UNCERTAIN:
            run.uncertain_count += 1
        elif classification == ChangeClassification.ERROR:
            run.error_count += 1
        elif classification == ChangeClassification.SKIPPED_UNCONFIGURED:
            run.skipped_unconfigured_count += 1
        elif classification == ChangeClassification.NO_MATERIAL_CHANGE:
            run.unchanged_count += 1
        elif classification == ChangeClassification.SOURCE_REMOVED:
            run.uncertain_count += 1
