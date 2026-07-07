"""Enrichment data for guest-facing validation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ValidationScopeItem:
    key: str
    label: str
    status: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class UploadedDocumentSummary:
    document_type: str
    document_id: str
    uploaded: bool
    original_filename: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReportEnrichment:
    validation_scope: tuple[ValidationScopeItem, ...]
    uploaded_documents: tuple[UploadedDocumentSummary, ...]
    validation_confidence: Decimal
    confidence_explanation: str
    checks_passed_count: int
    extraction_connected: bool = False

    def to_context_snapshot(self) -> dict:
        return {
            "validation_scope": [
                {
                    "key": item.key,
                    "label": item.label,
                    "status": item.status,
                    "reason": item.reason,
                }
                for item in self.validation_scope
            ],
            "uploaded_documents": [
                {
                    "document_type": doc.document_type,
                    "document_id": doc.document_id,
                    "uploaded": doc.uploaded,
                    "original_filename": doc.original_filename,
                }
                for doc in self.uploaded_documents
            ],
            "validation_confidence": str(self.validation_confidence),
            "confidence_explanation": self.confidence_explanation,
            "checks_passed_count": self.checks_passed_count,
            "extraction_connected": self.extraction_connected,
        }

    @classmethod
    def from_context_snapshot(cls, snapshot: dict) -> ValidationReportEnrichment | None:
        if not snapshot or "validation_scope" not in snapshot:
            return None
        return cls(
            validation_scope=tuple(
                ValidationScopeItem(
                    key=item["key"],
                    label=item["label"],
                    status=item["status"],
                    reason=item.get("reason"),
                )
                for item in snapshot["validation_scope"]
            ),
            uploaded_documents=tuple(
                UploadedDocumentSummary(
                    document_type=item["document_type"],
                    document_id=item["document_id"],
                    uploaded=item["uploaded"],
                    original_filename=item.get("original_filename"),
                )
                for item in snapshot.get("uploaded_documents", [])
            ),
            validation_confidence=Decimal(snapshot["validation_confidence"]),
            confidence_explanation=snapshot["confidence_explanation"],
            checks_passed_count=int(snapshot.get("checks_passed_count", 0)),
            extraction_connected=bool(snapshot.get("extraction_connected", False)),
        )
