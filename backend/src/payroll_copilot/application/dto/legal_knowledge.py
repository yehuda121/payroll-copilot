"""Legal knowledge DTOs — sync, proposals, vector index, RAG evaluation."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    WATCHED_SOURCE = "WATCHED_SOURCE"
    DISCOVERY_SOURCE = "DISCOVERY_SOURCE"


class AuthorityLevel(StrEnum):
    OFFICIAL = "OFFICIAL"
    SECONDARY_INTERPRETATION = "SECONDARY_INTERPRETATION"


class SyncTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class SyncRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"


class ChangeClassification(StrEnum):
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"
    NEW_RELEVANT_LAW = "NEW_RELEVANT_LAW"
    IRRELEVANT_CHANGE = "IRRELEVANT_CHANGE"
    SOURCE_REMOVED = "SOURCE_REMOVED"
    UNCERTAIN = "UNCERTAIN"
    NO_CHANGE = "NO_CHANGE"
    SKIPPED_UNCONFIGURED = "SKIPPED_UNCONFIGURED"
    ERROR = "ERROR"


class ProposalStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class LegalSourceRecord(BaseModel):
    source_id: str
    provider: str
    source_type: SourceType
    url: str | None = None
    authority_level: AuthorityLevel
    related_rule_ids: list[str] = Field(default_factory=list)
    enabled: bool = False
    notes: str = ""
    last_checked_at: datetime | None = None
    last_successful_sync: datetime | None = None
    last_content_hash: str | None = None
    coverage_status: str = "unconfigured"


class LegalChangeAnalysis(BaseModel):
    classification: ChangeClassification
    affected_rule_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    reasoning_summary: str = ""
    candidate_effective_date: date | None = None
    confidence: float | None = None
    requires_human_review: bool = True
    evidence_references: list[str] = Field(default_factory=list)


class LegalChangeProposal(BaseModel):
    proposal_id: str
    source_id: str
    classification: ChangeClassification
    affected_rule_ids: list[str] = Field(default_factory=list)
    old_snapshot_ref: str | None = None
    new_snapshot_ref: str | None = None
    old_content_hash: str | None = None
    new_content_hash: str | None = None
    diff_text: str = ""
    ai_summary: str = ""
    reasoning_summary: str = ""
    candidate_effective_date: date | None = None
    confidence: float | None = None
    requires_human_review: bool = True
    evidence_references: list[str] = Field(default_factory=list)
    status: ProposalStatus = ProposalStatus.PENDING_REVIEW
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None
    authority_level: AuthorityLevel = AuthorityLevel.SECONDARY_INTERPRETATION
    source_url: str | None = None
    sync_run_id: str | None = None


class SourceSyncOutcome(BaseModel):
    source_id: str
    classification: ChangeClassification
    message: str = ""
    proposal_id: str | None = None
    error: str | None = None
    content_hash: str | None = None


class LegalSyncRun(BaseModel):
    run_id: str
    trigger: SyncTrigger
    started_at: datetime
    completed_at: datetime | None = None
    status: SyncRunStatus = SyncRunStatus.RUNNING
    sources_checked: int = 0
    unchanged_count: int = 0
    irrelevant_change_count: int = 0
    material_change_count: int = 0
    new_relevant_count: int = 0
    uncertain_count: int = 0
    error_count: int = 0
    skipped_unconfigured_count: int = 0
    outcomes: list[SourceSyncOutcome] = Field(default_factory=list)
    triggered_by: str | None = None


class ApproveProposalRequest(BaseModel):
    effective_date: date
    confirm_effective_date: bool = False
    rule_yaml_override: dict[str, Any] | None = None
    new_rule_id: str | None = None
    new_rule_body: dict[str, Any] | None = None


class RejectProposalRequest(BaseModel):
    reason: str | None = None


class IndexedChunkMeta(BaseModel):
    chunk_id: str
    rule_id: str
    rule_version: str
    title: str = ""
    section: str = ""
    valid_from: date | None = None
    valid_to: date | None = None
    scope: str = "general"
    source_id: str | None = None
    source_reference: str | None = None
    authority_level: str = "OFFICIAL"
    content_hash: str = ""
    language: str = "he"
    approval_status: str = "approved"
    text: str = ""


class VectorIndexHealth(BaseModel):
    backend: str
    embedding_model: str | None = None
    indexed_rules: int = 0
    indexed_versions: int = 0
    chunk_count: int = 0
    last_indexed_at: datetime | None = None
    last_error: str | None = None
    status: str = "empty"


class RagEvalMetricValue(BaseModel):
    value: float | None = None
    status: str = "ok"  # ok | unavailable | error
    reason: str | None = None


class EvaluationCaseResult(BaseModel):
    case_id: str
    question: str
    reference_answer: str
    generated_answer: str = ""
    effective_date: date | None = None
    expected_rule_ids: list[str] = Field(default_factory=list)
    retrieved_rule_ids: list[str] = Field(default_factory=list)
    retrieved_versions: list[str] = Field(default_factory=list)
    retrieved_contexts: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_mode: str | None = None
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)
    # Deterministic retrieval metrics (rule-id based; no extra deps).
    retrieval_scores: list[float] = Field(default_factory=list)
    hit_at_5: bool | None = None
    recall_at_5: float | None = None
    mrr: float | None = None
    first_relevant_rank: int | None = None
    faithfulness: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    context_precision: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    context_recall: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    answer_relevancy: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    temporal_pass: bool | None = None
    temporal_detail: str | None = None
    error: str | None = None
    status: str = "pending"


class EvaluationRun(BaseModel):
    run_id: str
    dataset_version: str
    status: str = "RUNNING"
    started_at: datetime
    completed_at: datetime | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    case_count: int = 0
    completed_cases: int = 0
    failed_cases: int = 0
    faithfulness: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    context_precision: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    context_recall: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    answer_relevancy: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    temporal_accuracy: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    # Aggregate retrieval metrics across cases that have expected_rule_ids.
    hit_rate_at_5: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    recall_at_5: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    mrr: RagEvalMetricValue = Field(default_factory=RagEvalMetricValue)
    # Non-secret reproducibility snapshot for BEFORE/AFTER comparisons.
    baseline_config: dict[str, Any] = Field(default_factory=dict)
    triggered_by: str | None = None
    error: str | None = None
